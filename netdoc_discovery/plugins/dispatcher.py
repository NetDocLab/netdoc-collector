"""
Plugin dispatcher.

Maps (vendor, platform) tuples to plugin classes.
To add a new vendor/platform, simply import the plugin class and add
a new entry to PLUGIN_REGISTRY — no other file needs to change.

Example registry key: ("cisco", "ios") -> CiscoIOSPlugin
"""

import logging
from typing import Type
from .base import BasePlugin
from .netmiko_cisco_ios import NetmikoCiscoIOSPlugin


# ---------------------------------------------------------------------------
# Registry: (vendor, platform) -> plugin class
# ---------------------------------------------------------------------------

PLUGIN_REGISTRY: dict[tuple[str, str], Type[BasePlugin]] = {
    # 'http:panw:ngfw': NetmikoCiscoIOSPlugin,
    # 'http:vmware:vsphere': NetmikoCiscoIOSPlugin,
    # 'netmiko:allied_telesis:awplus': NetmikoAlliedTelesisAwplusPlugin,
    # 'netmiko:aruba:oscx': NetmikoArubaOSCXPlugin,
    'netmiko:cisco:ios': NetmikoCiscoIOSPlugin,  # TODO: should implement telnet
    # 'netmiko:cisco:nxos': NetmikoCiscoNXOSlugin,
    # 'netmiko:cisco:xr': NetmikoCiscoXRPlugin,
    # 'netmiko:hp:comware': NetmikoHPComwarePlugin,
    # 'netmiko:hp:procurve': NetmikoHPProcurvePlugin, # TODO: should implement telnet
    # 'netmiko:huawei:vrp': NetmikoHuaweiVRPPlugin,
    # 'netmiko:linux:ios': NetmikoCiscoIOSPlugin,
}


def get_plugin(plugin: str, host_name: str, host_data: dict, report_path=None) -> BasePlugin:
    """
    Instantiate and return the correct plugin for a given vendor/platform.

    Args:
        vendor:    e.g. "cisco"
        platform:  e.g. "ios"
        host_name: Nornir host name
        host_data: host.data dict from Nornir inventory

    Raises:
        ValueError: if no plugin is registered for the (vendor, platform) pair.
    """

    plugin_cls = PLUGIN_REGISTRY.get(plugin)

    if plugin_cls is None:
        for v, p in PLUGIN_REGISTRY:
            logging.debug('Registered plugin %s=%s', v, p)
        raise ValueError(f"No plugin registered for plugin='{plugin}'")

    return plugin_cls(host_name=host_name, host_data=host_data, report_path=report_path)
