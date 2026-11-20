from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def test_cisco_collectors_request_vrrp_group_detail_and_configuration():
    assert {'show vrrp all', 'show vrrp detail', 'show running-config'} <= set(
        NetmikoCiscoIosPlugin.commands()
    )
    assert {'show vrrp', 'show vrrpv3 all', 'show running-config'} <= set(
        NetmikoCiscoNxosPlugin.commands()
    )
