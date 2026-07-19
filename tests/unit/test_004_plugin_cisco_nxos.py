"""Tests for NetmikoCiscoNxosPlugin."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def plugin():
    """Minimal plugin instance with no report path."""
    return NetmikoCiscoNxosPlugin(
        host_name='nxos-switch-01',
        host_data={'netmiko_device_type': 'cisco_nxos'},
        report_path=None,
        cmd_timeout=30,
    )


@pytest.fixture
def mock_task():
    """Nornir Task mock with a cisco_nxos host."""
    task = MagicMock()
    task.host.name = 'nxos-switch-01'
    task.host.data = {'netmiko_device_type': 'cisco_nxos'}
    return task


# ---------------------------------------------------------------------------
# commands() — static method
# ---------------------------------------------------------------------------


class TestCommands:
    def test_no_vrf_returns_standard_commands(self):
        cmds = NetmikoCiscoNxosPlugin.commands()
        assert isinstance(cmds, list)
        assert len(cmds) > 0

    def test_no_vrf_contains_expected_commands(self):
        cmds = NetmikoCiscoNxosPlugin.commands()
        assert 'show version' in cmds
        assert 'show running-config' in cmds
        assert 'show interface' in cmds
        assert 'show vrf detail' in cmds

    def test_no_vrf_does_not_contain_vrf_suffix_commands(self):
        """Standard commands must not include per-VRF variants."""
        cmds = NetmikoCiscoNxosPlugin.commands()
        cmds.remove('show vrf detail')
        cmds.remove('show ip interface vrf all')
        cmds.remove('show ip route vrf all')
        vrf_cmds = [c for c in cmds if 'vrf' in c]
        assert vrf_cmds == [], f'Unexpected VRF commands in standard list: {vrf_cmds}'

    def test_no_vrf_contains_show_ip_route_vrf_all(self):
        """NX-OS uses 'show ip route vrf all' as a standard command, unlike IOS."""
        cmds = NetmikoCiscoNxosPlugin.commands()
        assert 'show ip route vrf all' in cmds

    def test_named_vrf_returns_one_command(self):
        cmds = NetmikoCiscoNxosPlugin.commands(vrf='MGMT')
        assert len(cmds) == 1

    def test_named_vrf_returns_vrf_aware_commands(self):
        cmds = NetmikoCiscoNxosPlugin.commands(vrf='MGMT')
        assert 'show ip arp vrf MGMT' in cmds

    def test_named_vrf_does_not_contain_plain_commands(self):
        cmds = NetmikoCiscoNxosPlugin.commands(vrf='MGMT')
        assert 'show ip arp' not in cmds
        assert 'show ip interface' not in cmds

    def test_named_vrf_interpolates_name(self):
        cmds = NetmikoCiscoNxosPlugin.commands(vrf='PROD_VRF')
        assert all('PROD_VRF' in c for c in cmds)

    def test_different_vrfs_produce_different_commands(self):
        assert NetmikoCiscoNxosPlugin.commands(vrf='A') != NetmikoCiscoNxosPlugin.commands(vrf='B')

    def test_nxos_has_nxos_specific_commands(self):
        """NX-OS plugin must include commands not present in IOS."""
        cmds = NetmikoCiscoNxosPlugin.commands()
        assert 'show hostname' in cmds
        assert 'show vpc' in cmds
        assert 'show vdc' in cmds
        assert 'show port-channel summary' in cmds

    def test_nxos_does_not_have_ios_only_commands(self):
        """NX-OS plugin must not include IOS-only commands."""
        cmds = NetmikoCiscoNxosPlugin.commands()
        assert 'show authentication sessions' not in cmds
        assert 'show dot1x all' not in cmds
        assert 'show switch' not in cmds


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

        for cmd in NetmikoCiscoNxosPlugin.commands():
            assert cmd in result['raw_outputs']

    def test_parsed_outputs_only_contains_non_none_results(self, plugin, mock_task):
        def side_effect(task, platform, cmd):
            if cmd == 'show version':
                return ('raw', [{'version': '9.3(10)'}])
            return ('raw', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect):
            result = plugin.collect(mock_task)

        assert 'show version' in result['parsed_outputs']
        assert 'show interface' not in result['parsed_outputs']

    def test_default_vrf_commands_always_run(self, plugin, mock_task):
        """'default' VRF is always added even when show vrf returns nothing."""
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)) as mock_cmd:
            plugin.collect(mock_task)

        called_cmds = [c.args[2] for c in mock_cmd.call_args_list]
        assert 'show ip arp vrf default' in called_cmds

    def test_named_vrf_commands_run_when_show_vrf_parsed(self, plugin, mock_task):
        show_vrf_parsed = [{'name': 'MGMT'}, {'name': 'PROD'}]

        def side_effect(task, platform, cmd):
            if cmd == 'show vrf detail':
                return ('raw vrf output', show_vrf_parsed)
            return ('raw', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect) as mock_cmd:
            plugin.collect(mock_task)

        called_cmds = [c.args[2] for c in mock_cmd.call_args_list]
        assert 'show ip arp vrf MGMT' in called_cmds
        assert 'show ip arp vrf PROD' in called_cmds

    def test_named_vrf_commands_not_run_when_show_vrf_not_parsed(self, plugin, mock_task):
        """If show vrf returns no parsed data, only default VRF commands run."""
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)) as mock_cmd:
            plugin.collect(mock_task)

        called_cmds = [c.args[2] for c in mock_cmd.call_args_list]
        called_cmds.remove('show vrf detail')
        called_cmds.remove('show ip interface vrf all')
        called_cmds.remove('show ip route vrf all')
        named_vrf_cmds = [c for c in called_cmds if 'vrf' in c and 'vrf default' not in c]
        assert named_vrf_cmds == []

    def test_run_netmiko_cmd_receives_correct_platform(self, plugin, mock_task):
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)) as mock_cmd:
            plugin.collect(mock_task)

        for c in mock_cmd.call_args_list:
            assert c.args[1] == 'cisco_nxos'

    def test_raw_output_stored_per_command(self, plugin, mock_task):
        def side_effect(task, platform, cmd):
            return (f'output of {cmd}', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect):
            result = plugin.collect(mock_task)

        assert result['raw_outputs']['show version'] == 'output of show version'
        assert result['raw_outputs']['show interface'] == 'output of show interface'

    def test_vrf_commands_output_stored_in_raw(self, plugin, mock_task):
        show_vrf_parsed = [{'name': 'MGMT'}]

        def side_effect(task, platform, cmd):
            if cmd == 'show vrf detail':
                return ('vrf raw', show_vrf_parsed)
            return (f'output of {cmd}', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect):
            result = plugin.collect(mock_task)

        assert 'show ip arp vrf MGMT' in result['raw_outputs']


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

        assert 'Stopping collection on nxos-switch-01 due to error' in caplog.text

    def test_returns_dict_even_on_early_exception(self, plugin, mock_task):
        with patch.object(plugin, 'run_netmiko_cmd', side_effect=Exception('boom')):
            result = plugin.collect(mock_task)

        assert isinstance(result, dict)
        assert 'raw_outputs' in result
        assert 'parsed_outputs' in result

    def test_partial_results_returned_before_exception(self, plugin, mock_task):
        """Commands executed before the failure should still appear in output."""
        standard_cmds = NetmikoCiscoNxosPlugin.commands()
        fail_at = standard_cmds[2]

        def side_effect(task, platform, cmd):
            if cmd == fail_at:
                raise Exception('timeout')
            return (f'output {cmd}', None)

        with patch.object(plugin, 'run_netmiko_cmd', side_effect=side_effect):
            result = plugin.collect(mock_task)

        for cmd in standard_cmds[:2]:
            assert cmd in result['raw_outputs']

    def test_missing_netmiko_device_type_uses_none(self, mock_task):
        """Plugin should not crash if netmiko_device_type is absent from host data."""
        mock_task.host.data = {}
        plugin = NetmikoCiscoNxosPlugin(
            host_name='nxos-switch-01',
            host_data={},
            report_path=None,
        )
        with patch.object(plugin, 'run_netmiko_cmd', return_value=('raw', None)):
            result = plugin.collect(mock_task)

        assert 'raw_outputs' in result
