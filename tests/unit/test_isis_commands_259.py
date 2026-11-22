from netdoc_collector.plugins.netmiko_cisco_ios import NetmikoCiscoIosPlugin
from netdoc_collector.plugins.netmiko_cisco_nxos import NetmikoCiscoNxosPlugin


def test_ios_captures_process_interface_and_native_adjacent_systems():
    assert {
        'show clns protocol',
        'show clns interface',
        'show isis neighbors detail',
        'show clns is-neighbors detail',
        'show isis hostname',
    } <= set(NetmikoCiscoIosPlugin.commands())


def test_nxos_captures_scoped_process_interface_and_native_identity():
    assert {
        'show isis protocol vrf all',
        'show isis interface vrf all',
        'show isis adjacency vrf all',
        'show isis hostname detail vrf all',
    } <= set(NetmikoCiscoNxosPlugin.commands())
    assert {
        'show isis protocol vrf RED',
        'show isis interface vrf RED',
        'show isis adjacency vrf RED',
        'show isis hostname detail vrf RED',
    } <= set(NetmikoCiscoNxosPlugin.commands('RED'))


def test_ios_collects_the_native_process_selector_under_its_configured_vrf():
    config = 'router isis RED-ISIS\n vrf RED\nrouter isis CORE\n net 49.0001.0000.0000.0001.00\n'
    red = NetmikoCiscoIosPlugin.commands('RED', config=config)
    default = NetmikoCiscoIosPlugin.commands('default', config=config)
    assert 'show clns RED-ISIS is-neighbors detail' in red
    assert 'show clns RED-ISIS is-neighbors detail' not in default
    assert 'show clns CORE is-neighbors detail' in default
