"""Tests for NetmikoCiscoIosPlugin."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def plugin():
    """Minimal plugin instance with no report path."""
    return NetmikoCiscoIosPlugin(
        host_name='router-01',
        host_data={'netmiko_device_type': 'cisco_ios'},
        report_path=None,
        cmd_timeout=30,
    )


@pytest.fixture
def mock_task():
    """Nornir Task mock with a cisco_ios host."""
    task = MagicMock()
    task.host.name = 'router-01'
    task.host.data = {'netmiko_device_type': 'cisco_ios'}
    return task


# ---------------------------------------------------------------------------
# commands() — static method
# ---------------------------------------------------------------------------


class TestCommands:
    def test_no_vrf_returns_standard_commands(self):
        cmds = NetmikoCiscoIosPlugin.commands()
        assert isinstance(cmds, list)
        assert len(cmds) > 0

    def test_no_vrf_contains_expected_commands(self):
        cmds = NetmikoCiscoIosPlugin.commands()
        assert 'show version' in cmds
        assert 'show running-config' in cmds
        assert 'show interfaces' in cmds
        assert 'show vrf' in cmds

    def test_no_vrf_does_not_contain_vrf_commands(self):
        cmds = NetmikoCiscoIosPlugin.commands()
        cmds.remove('show vrf')
        assert not any('vrf' in c for c in cmds)

    def test_default_vrf_returns_two_commands(self):
        cmds = NetmikoCiscoIosPlugin.commands(vrf='default')
        assert cmds == ['show ip arp', 'show ip route']

    def test_named_vrf_returns_vrf_aware_commands(self):
        cmds = NetmikoCiscoIosPlugin.commands(vrf='MGMT')
        assert 'show ip arp vrf MGMT' in cmds
        assert 'show ip route vrf MGMT' in cmds

    def test_named_vrf_does_not_contain_plain_commands(self):
        cmds = NetmikoCiscoIosPlugin.commands(vrf='MGMT')
        assert 'show ip arp' not in cmds
        assert 'show ip route' not in cmds

    def test_named_vrf_interpolates_name(self):
        cmds = NetmikoCiscoIosPlugin.commands(vrf='PROD_VRF')
        assert all('PROD_VRF' in c for c in cmds)


# ---------------------------------------------------------------------------
# collect() — happy path
# ---------------------------------------------------------------------------


class TestCollectHappyPath:
    def test_returns_raw_and_parsed_keys(self, plugin, mock_task):
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)):
            result = plugin.collect(mock_task)

        assert 'raw_outputs' in result
        assert 'parsed_outputs' in result

    def test_raw_outputs_contains_all_standard_commands(self, plugin, mock_task):
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)):
            result = plugin.collect(mock_task)

        for cmd in NetmikoCiscoIosPlugin.commands():
            assert cmd in result['raw_outputs']

    def test_parsed_outputs_only_contains_non_none_results(self, plugin, mock_task):
        def side_effect(task, platform, cmd):
            if cmd == 'show version':
                return ('raw', [{'version': '15.2'}])
            return ('raw', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect):
            result = plugin.collect(mock_task)

        assert 'show version' in result['parsed_outputs']
        assert 'show interfaces' not in result['parsed_outputs']

    def test_default_vrf_commands_always_run(self, plugin, mock_task):
        """'default' VRF is always added even when show vrf returns nothing."""
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)) as mock_cmd:
            plugin.collect(mock_task)

        called_cmds = [c.args[2] for c in mock_cmd.call_args_list]
        assert 'show ip arp' in called_cmds
        assert 'show ip route' in called_cmds

    def test_named_vrf_commands_run_when_show_vrf_parsed(self, plugin, mock_task):
        """Named VRF commands are executed when show vrf returns VRF entries."""
        show_vrf_parsed = [{'name': 'MGMT'}, {'name': 'PROD'}]

        def side_effect(task, platform, cmd):
            if cmd == 'show vrf':
                return ('raw vrf output', show_vrf_parsed)
            return ('raw', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect) as mock_cmd:
            plugin.collect(mock_task)

        called_cmds = [c.args[2] for c in mock_cmd.call_args_list]
        assert 'show ip arp vrf MGMT' in called_cmds
        assert 'show ip route vrf MGMT' in called_cmds
        assert 'show ip arp vrf PROD' in called_cmds
        assert 'show ip route vrf PROD' in called_cmds

    def test_run_netmiko_cmd_receives_correct_platform(self, plugin, mock_task):
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)) as mock_cmd:
            plugin.collect(mock_task)

        for c in mock_cmd.call_args_list:
            assert c.args[1] == 'cisco_ios'

    def test_raw_output_stored_per_command(self, plugin, mock_task):
        def side_effect(task, platform, cmd):
            return (f'output of {cmd}', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect):
            result = plugin.collect(mock_task)

        assert result['raw_outputs']['show version'] == 'output of show version'
        assert result['raw_outputs']['show interfaces'] == 'output of show interfaces'


# ---------------------------------------------------------------------------
# collect() — error handling
# ---------------------------------------------------------------------------


class TestCollectErrorHandling:
    def test_exception_is_caught_and_logged(self, plugin, mock_task, caplog):
        with (
            patch.object(plugin, 'run_netmiko_cmd', side_effect=Exception('connection reset')),
            caplog.at_level(logging.ERROR),
        ):
            plugin.collect(mock_task)

        assert 'Stopping collection on router-01 due to error' in caplog.text

    def test_returns_dict_even_on_early_exception(self, plugin, mock_task):
        with patch.object(plugin, 'run_netmiko_cmd', side_effect=Exception('boom')):
            result = plugin.collect(mock_task)

        assert isinstance(result, dict)
        assert 'raw_outputs' in result
        assert 'parsed_outputs' in result

    def test_partial_results_returned_before_exception(self, plugin, mock_task):
        """Commands executed before the failure should still appear in output."""
        standard_cmds = NetmikoCiscoIosPlugin.commands()
        fail_at = standard_cmds[2]

        def side_effect(task, platform, cmd):
            if cmd == fail_at:
                raise Exception('timeout')
            return (f'output {cmd}', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect):
            result = plugin.collect(mock_task)

        # Commands before the failing one must be present
        for cmd in standard_cmds[:2]:
            assert cmd in result['raw_outputs']

    def test_missing_netmiko_device_type_uses_none(self, mock_task):
        """Plugin should not crash if netmiko_device_type is absent from host data."""
        mock_task.host.data = {}
        plugin = NetmikoCiscoIosPlugin(
            host_name='router-01',
            host_data={},
            report_path=None,
        )
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)):
            result = plugin.collect(mock_task)

        assert 'raw_outputs' in result
