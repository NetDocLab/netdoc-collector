import pytest

from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


@pytest.mark.parametrize('plugin', [NetmikoCiscoIosPlugin, NetmikoCiscoNxosPlugin])
def test_cisco_collectors_request_unfiltered_glbp_detail_in_the_device_pass(plugin):
    assert plugin.commands().count('show glbp') == 1
    assert 'show glbp' not in plugin.commands(vrf='default')
    assert 'show glbp' not in plugin.commands(vrf='tenant-vrf')
