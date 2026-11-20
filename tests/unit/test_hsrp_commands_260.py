from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def test_cisco_collector_requests_full_native_hsrp_group_details():
    assert {'show standby', 'show standby all'} <= set(NetmikoCiscoIosPlugin.commands())
    assert 'show hsrp all' in NetmikoCiscoNxosPlugin.commands()
