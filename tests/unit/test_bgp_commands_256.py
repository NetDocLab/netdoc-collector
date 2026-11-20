"""Check the collector's scoped BGP acquisition contract."""

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def test_ios_schedules_ipv6_default_and_named_vrf_detail():
    assert 'show bgp ipv6 unicast neighbors' in NetmikoCiscoIosPlugin.commands()
    assert 'show ip bgp vpnv4 vrf WAN neighbors' in NetmikoCiscoIosPlugin.commands(vrf='WAN')


def test_nxos_schedules_all_families_in_each_discovered_vrf():
    commands = NetmikoCiscoNxosPlugin.commands(vrf='WAN')
    assert 'show bgp vrf WAN all neighbors' in commands
    assert 'show ip bgp neighbors vrf WAN' in commands
