"""OSPFv3 schedules use the existing command-keyed collection transport."""

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def test_ios_schedules_family_specific_and_legacy_operation():
    commands = NetmikoCiscoIosPlugin.commands()
    assert 'show ospfv3' in commands
    for operation in ('interface', 'neighbor detail', 'virtual-links'):
        assert f'show ipv6 ospf {operation}' in commands
        for family in ('ipv4', 'ipv6'):
            assert f'show ospfv3 {family} {operation}' in commands


def test_nxos_schedules_native_wrappers_for_all_reported_contexts():
    commands = NetmikoCiscoNxosPlugin.commands()
    for operation in ('', ' interface', ' neighbors detail', ' virtual-links'):
        assert f'show ospfv3{operation} vrf all | json' in commands
