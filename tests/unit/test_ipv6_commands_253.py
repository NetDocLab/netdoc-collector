"""Public command selection only; no devices or native captures are involved."""

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def test_ios_default_context_selects_ipv6_interface_neighbor_route_and_onlink_sources():
    standard = NetmikoCiscoIosPlugin.commands()
    default = NetmikoCiscoIosPlugin.commands(vrf='default')
    assert 'show ipv6 interface' in standard
    assert {'show ipv6 neighbors', 'show ipv6 route', 'show ipv6 nd on-link prefix'} <= set(default)
    assert len(standard) == len(set(standard))
    assert len(default) == len(set(default))


def test_ios_named_context_requests_scoped_ipv6_sources():
    commands = NetmikoCiscoIosPlugin.commands(vrf='BLUE')
    assert {
        'show ipv6 neighbors vrf BLUE',
        'show ipv6 route vrf BLUE',
        'show ipv6 nd on-link prefix vrf BLUE',
    } <= set(commands)
    assert 'show ipv6 neighbors' not in commands
    assert len(commands) == len(set(commands))


def test_nxos_requests_all_context_ipv6_sources_once():
    commands = NetmikoCiscoNxosPlugin.commands()
    assert {
        'show ipv6 interface vrf all',
        'show ipv6 neighbor vrf all',
        'show ipv6 route vrf all',
    } <= set(commands)
    assert len(commands) == len(set(commands))
    assert not any(
        command.startswith('show ipv6') for command in NetmikoCiscoNxosPlugin.commands(vrf='BLUE')
    )
