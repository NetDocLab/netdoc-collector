"""Plugin dispatcher for NetDoc collector plugins.

The dispatcher maps plugin identifiers to their implementation classes.
"""

import logging

from .base import BasePlugin
from .netmiko_allied_telesis_awplus import NetmikoAlliedTelesisAwplusPlugin
from .netmiko_aruba_oscx import NetmikoArubaOscxPlugin
from .netmiko_cisco_ios import NetmikoCiscoIosPlugin
from .netmiko_cisco_nxos import NetmikoCiscoNxosPlugin
from .netmiko_cisco_xr import NetmikoCiscoXrPlugin
from .netmiko_hp_comware import NetmikoHpComwarePlugin
from .netmiko_hp_procurve import NetmikoHpProcurvePlugin
from .netmiko_huawei_vrp import NetmikoHuaweiVrpPlugin
from .netmiko_linux import NetmikoLinuxAnyPlugin

# ---------------------------------------------------------------------------
# Registry: (vendor, platform) -> plugin class
# ---------------------------------------------------------------------------

PLUGIN_REGISTRY: dict[str, type[BasePlugin]] = {
    'netmiko:allied_telesis:awplus:ssh': NetmikoAlliedTelesisAwplusPlugin,
    'netmiko:aruba:oscx:ssh': NetmikoArubaOscxPlugin,
    'netmiko:cisco:ios:ssh': NetmikoCiscoIosPlugin,
    'netmiko:cisco:ios:telnet': NetmikoCiscoIosPlugin,
    'netmiko:cisco:nxos:ssh': NetmikoCiscoNxosPlugin,
    'netmiko:cisco:xr:ssh': NetmikoCiscoXrPlugin,
    'netmiko:hp:comware:ssh': NetmikoHpComwarePlugin,
    'netmiko:hp:procurve:ssh': NetmikoHpProcurvePlugin,
    'netmiko:hp:procurve:telnet': NetmikoHpProcurvePlugin,
    'netmiko:huawei:vrp:ssh': NetmikoHuaweiVrpPlugin,
    'netmiko:linux::ssh': NetmikoLinuxAnyPlugin,
    # 'netdoc:panw:ngfw:https': NetDocPanwNgfwHttpslugin,
    # 'netdoc:vmware:vsphere:https': NetDocVmwareVsphereHttpsPlugin,
}


def get_plugin(plugin: str, *args, **kwargs) -> BasePlugin:
    """Instantiate the configured plugin for a registered NetDoc platform.

    Args:
        plugin (str): plugin identifier key, for example "netmiko:cisco:ios:ssh".
        *args: positional arguments forwarded to the plugin constructor.
        **kwargs: keyword arguments forwarded to the plugin constructor.

    Raises:
        ValueError: if no plugin is registered for the requested plugin key.
    """

    plugin_cls = PLUGIN_REGISTRY.get(plugin)

    if plugin_cls is None:
        for plugin_key, plugin_class in PLUGIN_REGISTRY.items():
            logging.debug('Registered plugin %s=%s', plugin_key, plugin_class)
        raise ValueError(f"No plugin registered for plugin='{plugin}'")

    return plugin_cls(*args, **kwargs)
