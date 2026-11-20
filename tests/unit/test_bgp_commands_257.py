"""Advanced BGP acquisition through the existing Cisco command planners."""

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def test_ios_schedules_session_and_policy_template_detail():
    commands = NetmikoCiscoIosPlugin.commands()
    assert 'show ip bgp template peer-session' in commands
    assert 'show ip bgp template peer-policy' in commands
    assert 'show ip bgp vpnv6 unicast vrf WAN neighbors' in NetmikoCiscoIosPlugin.commands(
        vrf='WAN'
    )


def test_nxos_uses_configured_template_names_and_native_vrf_scope():
    config = (
        'router bgp 65001\n'
        '  template peer SHARED\n'
        '    inherit peer-session BASE\n'
        '  template peer-session BASE\n'
        '  vrf WAN\n'
        '    template peer-policy WAN-POLICY\n'
        '    template peer NAME|invalid\n'
        'router ospf 1\n'
        '  template peer UNRELATED\n'
    )
    assert [
        command
        for command in NetmikoCiscoNxosPlugin.commands(vrf='default', config=config)
        if 'peer-' in command
    ] == [
        'show bgp peer-template SHARED',
        'show bgp peer-session BASE',
    ]
    assert [
        command
        for command in NetmikoCiscoNxosPlugin.commands(vrf='WAN', config=config)
        if 'peer-' in command
    ] == [
        'show bgp peer-policy WAN-POLICY vrf WAN',
    ]
