"""Scoped Catalyst operational system MTU acquisition."""

from types import SimpleNamespace

import pytest

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin


@pytest.mark.parametrize(
    ('version', 'collect_mtu'),
    [
        ({'hardware': ['C9500-48Y4C', 'C9500-48Y4C'], 'version': '17.3.4'}, True),
        ({'hardware': ['C9500-24Y4C'], 'version': '17.03.04'}, True),
        ({'hardware': ['C9500-48Y4C'], 'version': '16.9.1'}, False),
        ({'hardware': ['C9300-48P'], 'version': '17.3.4'}, False),
        ({}, False),
    ],
)
def test_system_mtu_probe_is_device_scoped_and_preserves_its_raw_result(
    monkeypatch, version, collect_mtu
):
    probe = 'show system mtu'
    native = 'Global Ethernet MTU is 1500 bytes.\r\n'
    plugin = NetmikoCiscoIosPlugin('target', {}, None)
    calls = []

    def run_command(task, platform, command):
        calls.append(command)
        if command == 'show version':
            return 'IOS XE version', [version] if version else None
        if command == 'show vrf':
            return 'VRF list', [{'name': 'RED'}, {'name': 'BLUE'}]
        if command == probe:
            return native, None
        return '', None

    monkeypatch.setattr(plugin, 'run_netmiko_cmd', run_command)
    task = SimpleNamespace(
        host=SimpleNamespace(name='target', data={'netmiko_device_type': 'cisco_ios'})
    )
    wrapper = plugin.collect(task)
    assert calls.count(probe) == int(collect_mtu)
    if collect_mtu:
        assert calls.index(probe) > calls.index('show version')
        assert calls.index(probe) > calls.index('show ip route vrf BLUE')
        assert wrapper['raw_outputs'][probe] == native
        assert probe not in wrapper['parsed_outputs']
    else:
        assert probe not in wrapper['raw_outputs']
