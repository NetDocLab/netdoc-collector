"""Unit tests for the BasePlugin abstract class and its shared helpers."""

import json
import logging
from unittest.mock import MagicMock

import pytest
from nornir.core.exceptions import NornirSubTaskError
from textfsm.parser import TextFSMError

from netdoc_collector.plugins import base as base_module
from netdoc_collector.plugins.base import BasePlugin


class ConcretePlugin(BasePlugin):
    """Minimal concrete subclass, since BasePlugin.collect is abstract."""

    def collect(self, task):
        return {}


# ─────────────────────────────────────────────
#  __init__
# ─────────────────────────────────────────────


class TestInit:
    def test_basic_attributes_set(self):
        plugin = ConcretePlugin(
            host_name='device-1', host_data={'k': 'v'}, report_path=None, cmd_timeout=99
        )

        assert plugin.host_name == 'device-1'
        assert plugin.host_data == {'k': 'v'}
        assert plugin.cmd_timeout == 99
        assert plugin.report_path is None

    def test_default_cmd_timeout(self):
        plugin = ConcretePlugin(host_name='device-1', host_data={}, report_path=None)
        assert plugin.cmd_timeout == 240

    def test_report_path_creates_host_subdirectory(self, tmp_path):
        plugin = ConcretePlugin(host_name='device-1', host_data={}, report_path=tmp_path)

        expected = tmp_path / 'device-1'
        assert plugin.report_path == expected
        assert expected.is_dir()

    def test_report_path_none_when_not_provided(self):
        plugin = ConcretePlugin(host_name='device-1', host_data={}, report_path=None)
        assert plugin.report_path is None

    def test_report_path_is_idempotent_across_instances(self, tmp_path):
        """mkdir(exist_ok=True) must not raise if the directory already exists."""
        ConcretePlugin(host_name='device-1', host_data={}, report_path=tmp_path)
        # Second plugin for the same host/report_path must not raise.
        plugin2 = ConcretePlugin(host_name='device-1', host_data={}, report_path=tmp_path)
        assert plugin2.report_path.is_dir()

    def test_cannot_instantiate_abstract_class_directly(self):
        with pytest.raises(TypeError):
            BasePlugin(host_name='x', host_data={}, report_path=None)


# ─────────────────────────────────────────────
#  parse_netmiko_output
# ─────────────────────────────────────────────


class TestParseNetmikoOutput:
    def test_returns_parsed_list(self, monkeypatch):
        monkeypatch.setattr(base_module, 'get_structured_data', lambda _raw, **_kw: [{'a': 1}])

        result = BasePlugin.parse_netmiko_output('raw', 'cisco_ios', 'show version')

        assert result == [{'a': 1}]

    def test_returns_none_when_parsed_output_is_not_a_list(self, monkeypatch):
        """e.g. TextFSM returns the raw string itself when no template matches."""
        monkeypatch.setattr(base_module, 'get_structured_data', lambda _raw, **_kw: 'not a list')

        result = BasePlugin.parse_netmiko_output('raw', 'cisco_ios', 'show version')

        assert result is None

    def test_returns_none_on_textfsm_error(self, monkeypatch):
        def raise_textfsm_error(raw, **kw):
            raise TextFSMError('bad template')

        monkeypatch.setattr(base_module, 'get_structured_data', raise_textfsm_error)

        result = BasePlugin.parse_netmiko_output('raw', 'cisco_ios', 'show ip route vrf default')

        assert result is None

    def test_logs_warning_only_for_vrf_commands_on_failure(self, monkeypatch, caplog):
        def raise_textfsm_error(_raw, **_kw):
            raise TextFSMError('bad template')

        monkeypatch.setattr(base_module, 'get_structured_data', raise_textfsm_error)

        with caplog.at_level(logging.WARNING, logger=base_module.__name__):
            BasePlugin.parse_netmiko_output('raw', 'cisco_ios', 'show vrf')
        assert any('Cannot parse command' in r.message for r in caplog.records)

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=base_module.__name__):
            BasePlugin.parse_netmiko_output('raw', 'cisco_ios', 'show version')
        assert caplog.records == []

    def test_passes_platform_and_cmd_to_get_structured_data(self, monkeypatch):
        mock_get_structured_data = MagicMock(return_value=[])
        monkeypatch.setattr(base_module, 'get_structured_data', mock_get_structured_data)

        BasePlugin.parse_netmiko_output('raw text', 'cisco_nxos', 'show version')

        mock_get_structured_data.assert_called_once_with(
            'raw text', platform='cisco_nxos', command='show version'
        )


# ─────────────────────────────────────────────
#  slugify
# ─────────────────────────────────────────────


class TestSlugify:
    @pytest.mark.parametrize(
        'text,expected',
        [
            ('show running-config', 'show-running-config'),
            ('Show IP Route', 'show-ip-route'),
            ('  spaced out  ', 'spaced-out'),
            ('show vrf VRF_NAME', 'show-vrf-vrf-name'),
            ('---leading-trailing---', 'leading-trailing'),
            ('show ip route vrf default', 'show-ip-route-vrf-default'),
            ('a__b   c', 'a-b-c'),
        ],
    )
    def test_slugify_cases(self, text, expected):
        assert BasePlugin.slugify(text) == expected

    def test_empty_string(self):
        assert BasePlugin.slugify('') == ''

    def test_only_special_characters(self):
        assert BasePlugin.slugify('!!!???') == ''


# ─────────────────────────────────────────────
#  run_netmiko_cmd
# ─────────────────────────────────────────────


def _make_task(secret=None, check_enable_mode_result=True):
    """Build a fake Nornir Task with a mockable host connection and task.run."""
    net_connect = MagicMock()
    net_connect.secret = secret
    net_connect.check_enable_mode.return_value = check_enable_mode_result

    host = MagicMock()
    host.get_connection.return_value = net_connect

    nornir = MagicMock()
    task = MagicMock()
    task.host = host
    task.nornir = nornir
    return task, net_connect


class TestRunNetmikoCmd:
    def test_happy_path_returns_raw_and_parsed(self, monkeypatch):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task, _net_connect = _make_task(secret=None)
        cmd_result = MagicMock()
        cmd_result.result = 'raw output text'
        task.run.return_value = cmd_result

        monkeypatch.setattr(
            plugin, 'parse_netmiko_output', lambda _raw, _platform, _cmd: [{'x': 1}]
        )
        monkeypatch.setattr(plugin, 'write_output', MagicMock())

        raw, parsed = plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')

        assert raw == 'raw output text'
        assert parsed == [{'x': 1}]

    def test_enters_enable_mode_when_secret_set_and_not_already_enabled(self):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task, net_connect = _make_task(secret='enable-secret', check_enable_mode_result=False)
        cmd_result = MagicMock()
        cmd_result.result = 'output'
        task.run.return_value = cmd_result

        plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')

        net_connect.enable.assert_called_once()

    def test_skips_enable_mode_when_already_enabled(self):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task, net_connect = _make_task(secret='enable-secret', check_enable_mode_result=True)
        cmd_result = MagicMock()
        cmd_result.result = 'output'
        task.run.return_value = cmd_result

        plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')

        net_connect.enable.assert_not_called()

    def test_skips_enable_mode_when_no_secret(self):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task, net_connect = _make_task(secret=None)
        cmd_result = MagicMock()
        cmd_result.result = 'output'
        task.run.return_value = cmd_result

        plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')

        net_connect.enable.assert_not_called()
        net_connect.check_enable_mode.assert_not_called()

    def test_get_connection_failure_is_reraised(self):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task = MagicMock()
        task.host.get_connection.side_effect = RuntimeError('connection refused')

        with pytest.raises(RuntimeError, match='connection refused'):
            plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')

    def test_writes_raw_and_parsed_output(self, monkeypatch):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task, _ = _make_task()
        cmd_result = MagicMock()
        cmd_result.result = 'raw text'
        task.run.return_value = cmd_result
        monkeypatch.setattr(
            plugin, 'parse_netmiko_output', lambda _raw, _platform, _cmd: ['parsed']
        )
        mock_write = MagicMock()
        monkeypatch.setattr(plugin, 'write_output', mock_write)

        plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')

        assert mock_write.call_count == 2
        mock_write.assert_any_call('raw text', 'show version')
        mock_write.assert_any_call(['parsed'], 'show version')

    def test_nornir_sub_task_error_with_auth_exception_is_reraised(self, monkeypatch):
        from netmiko.exceptions import NetmikoAuthenticationException

        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task, _ = _make_task()

        inner_result = MagicMock()
        inner_result.exception = NetmikoAuthenticationException('bad creds')
        error = NornirSubTaskError(task=task, result=inner_result)
        task.run.side_effect = error

        with pytest.raises(NornirSubTaskError):
            plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')

    def test_nornir_sub_task_error_with_timeout_exception_is_reraised(self, monkeypatch):
        from netmiko.exceptions import NetmikoTimeoutException

        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task, _ = _make_task()

        inner_result = MagicMock()
        inner_result.exception = NetmikoTimeoutException('timed out')
        error = NornirSubTaskError(task=task, result=inner_result)
        task.run.side_effect = error

        with pytest.raises(NornirSubTaskError):
            plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')

    def test_nornir_sub_task_error_with_other_exception_is_reraised(self, monkeypatch):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        task, _ = _make_task()

        inner_result = MagicMock()
        inner_result.exception = RuntimeError('something else')
        error = NornirSubTaskError(task=task, result=inner_result)
        task.run.side_effect = error

        with pytest.raises(NornirSubTaskError):
            plugin.run_netmiko_cmd(task, 'cisco_ios', 'show version')


# ─────────────────────────────────────────────
#  write_output
# ─────────────────────────────────────────────


class TestWriteOutput:
    def test_noop_when_report_path_is_none(self, tmp_path):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=None)
        plugin.write_output('some content', 'show version')
        # No exception, nothing written anywhere — nothing to assert on disk.

    def test_noop_when_content_is_empty(self, tmp_path):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=tmp_path)
        plugin.write_output('', 'show version')
        plugin.write_output(None, 'show version')
        plugin.write_output([], 'show version')

        assert list(plugin.report_path.iterdir()) == []

    def test_writes_raw_text_file(self, tmp_path):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=tmp_path)
        plugin.write_output('raw device output', 'show version')

        out_file = plugin.report_path / 'show-version.raw'
        assert out_file.exists()
        assert out_file.read_text() == 'raw device output'

    def test_writes_json_file_for_list_content(self, tmp_path):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=tmp_path)
        plugin.write_output([{'a': 1}], 'show version')

        out_file = plugin.report_path / 'show-version.json'
        assert out_file.exists()
        assert json.loads(out_file.read_text()) == [{'a': 1}]

    def test_writes_json_file_for_dict_content(self, tmp_path):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=tmp_path)
        plugin.write_output({'k': 'v'}, 'show vrf')

        out_file = plugin.report_path / 'show-vrf.json'
        assert out_file.exists()
        assert json.loads(out_file.read_text()) == {'k': 'v'}

    def test_filename_is_slugified(self, tmp_path):
        plugin = ConcretePlugin(host_name='dev1', host_data={}, report_path=tmp_path)
        plugin.write_output('data', 'show ip route vrf default')

        assert (plugin.report_path / 'show-ip-route-vrf-default.raw').exists()
