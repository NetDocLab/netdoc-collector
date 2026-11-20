"""EIGRP commands preserve the observed process and family axes."""

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def test_iosxe_schedules_named_family_from_its_configured_vrf_and_as():
    config = (
        'router eigrp FABRIC\n'
        ' address-family ipv6 unicast vrf EDGE autonomous-system 200\n'
        ' exit-address-family\n'
        ' address-family ipv4 unicast vrf RED autonomous-system 300\n'
        ' exit-address-family\n'
    )
    commands = NetmikoCiscoIosPlugin.commands(vrf='EDGE', config=config)
    assert [command for command in commands if command.startswith('show eigrp ')] == [
        'show eigrp address-family ipv6 vrf EDGE 200 neighbors detail',
        'show eigrp address-family ipv6 vrf EDGE 200 interfaces detail',
    ]


def test_nxos_schedules_detail_for_the_native_tag_and_family_in_each_vrf():
    config = (
        'router eigrp FABRIC\n'
        '  autonomous-system 100\n'
        '  vrf EDGE\n'
        '    autonomous-system 200\n'
        '    address-family ipv6 unicast\n'
        '      autonomous-system 201\n'
        'router ospf UNRELATED\n'
        '  vrf EDGE\n'
    )
    commands = NetmikoCiscoNxosPlugin.commands(vrf='EDGE', config=config)
    assert [command for command in commands if 'eigrp' in command] == [
        'show ip eigrp FABRIC neighbors detail vrf EDGE',
        'show ip eigrp FABRIC interfaces brief vrf EDGE',
        'show ipv6 eigrp FABRIC neighbors detail vrf EDGE',
        'show ipv6 eigrp FABRIC interfaces brief vrf EDGE',
    ]
