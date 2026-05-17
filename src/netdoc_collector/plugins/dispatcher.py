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

# from .netmiko_aruba_oscx import NetmikoArubaOSCXPlugin
from .netmiko_cisco_ios import NetmikoCiscoIosSshPlugin

# from .netmiko_cisco_nxos import NetmikoCiscoNXOSPlugin
# from .netmiko_cisco_xr import NetmikoCiscoXRPlugin
# from .netmiko_hp_comware import NetmikoHPComwarePlugin
# from .netmiko_hp_procurve import NetmikoHPProcurvePlugin
# from .netmiko_huawei_vrp import NetmikoHuaweiVRPPlugin
# from .netmiko_linux import NetmikoLinuxPlugin
# from .netmiko_allied_telesis_awplus import NetmikoAlliedTelesisAwplusPlugin

# ---------------------------------------------------------------------------
# Registry: (vendor, platform) -> plugin class
# ---------------------------------------------------------------------------

PLUGIN_REGISTRY: dict[tuple[str, str], Type[BasePlugin]] = {
    # 'netmiko:allied_telesis:awplus:ssh': NetmikoAlliedTelesisAwplusSshPlugin,
    # 'netmiko:aruba:oscx:ssh': NetmikoArubaOscxSshPlugin,
    'netmiko:cisco:ios:ssh': NetmikoCiscoIosSshPlugin,
    # 'netmiko:cisco:ios:telnet': NetmikoCiscoIosTelnetPlugin,
    # 'netmiko:cisco:nxos:ssh': NetmikoCiscoNxosSshPlugin,
    # 'netmiko:cisco:xr:ssh': NetmikoCiscoXrSshPlugin,
    # 'netmiko:hp:comware:ssh': NetmikoHpComwareSshPlugin,
    # 'netmiko:hp:procurve:ssh': NetmikoHpProcurveSshPlugin,
    # 'netmiko:hp:procurve:telnet': NetmikoHpProcurveTelnetPlugin,
    # 'netmiko:huawei:vrp:ssh': NetmikoHuaweiVrpSshPlugin,
    # 'netmiko:linux::ssh': NetmikoLinuxAnySshPlugin,
    # 'netdoc:panw:ngfw:https': NetDocPanwNgfwHttpslugin,
    # 'netdoc:vmware:vsphere:https': NetDocVmwareVsphereHttpsPlugin,
}


def get_plugin(plugin: str, *args, **kwargs) -> BasePlugin:
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

    return plugin_cls(*args, **kwargs)
