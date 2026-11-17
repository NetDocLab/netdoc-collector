"""Public OSPF collection scheduling tests with a stubbed command adapter."""

from types import SimpleNamespace

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def _plugin(plugin_type, *, vrf_command, vrfs):
    plugin = plugin_type('router', {'netmiko_device_type': 'test'}, report_path=None)
    calls = []

    def run_netmiko_cmd(task, platform, command):
        calls.append(command)
        if command == vrf_command:
            return f'raw:{command}', [{'name': name} for name in vrfs]
        parsed = [{'command': command}] if command.startswith('show ip ospf') else None
        return f'raw:{command}', parsed

    plugin.run_netmiko_cmd = run_netmiko_cmd
    task = SimpleNamespace(
        host=SimpleNamespace(
            data={'netmiko_device_type': 'test'},
            name='router',
        )
    )
    return plugin, task, calls


def test_ios_schedules_process_and_interface_reads_once_and_preserves_wrapper():
    standard = NetmikoCiscoIosPlugin.commands()
    assert {'show ip ospf', 'show ip ospf interface', 'show ip ospf neighbor'} <= set(standard)
    assert len(standard) == len(set(standard))

    plugin, task, calls = _plugin(
        NetmikoCiscoIosPlugin,
        vrf_command='show vrf',
        vrfs=['default', 'BLUE', 'blue', 'BLUE'],
    )
    result = plugin.collect(task)
    assert calls.count('show ip ospf') == 1
    assert calls.count('show ip ospf interface') == 1
    assert calls.count('show ip ospf neighbor') == 1
    assert 'show ip ospf vrf BLUE' not in calls
    assert calls.count('show ip arp vrf BLUE') == 1
    assert calls.count('show ip arp vrf blue') == 1
    assert result['raw_outputs']['show ip ospf'] == 'raw:show ip ospf'
    assert result['parsed_outputs']['show ip ospf interface'] == [
        {'command': 'show ip ospf interface'}
    ]


def test_nxos_schedules_default_and_named_process_reads_once_and_preserves_wrapper():
    vrf_commands = NetmikoCiscoNxosPlugin.commands(vrf='BLUE')
    assert {'show ip ospf vrf BLUE', 'show ip ospf interface vrf BLUE'} <= set(vrf_commands)
    assert len(vrf_commands) == len(set(vrf_commands))

    plugin, task, calls = _plugin(
        NetmikoCiscoNxosPlugin,
        vrf_command='show vrf detail',
        vrfs=['default', 'BLUE', 'blue', 'BLUE'],
    )
    result = plugin.collect(task)
    for command in (
        'show ip ospf vrf default',
        'show ip ospf interface vrf default',
        'show ip ospf vrf BLUE',
        'show ip ospf interface vrf BLUE',
        'show ip ospf vrf blue',
        'show ip ospf interface vrf blue',
    ):
        assert calls.count(command) == 1
        assert result['raw_outputs'][command] == f'raw:{command}'
        assert result['parsed_outputs'][command] == [{'command': command}]
    assert calls.count('show ip ospf neighbor vrf all') == 1
