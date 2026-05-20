"""
Plugin for Cisco NX-OS devices.
"""

import logging
from nornir.core.task import Task
from .base import BasePlugin


class NetmikoCiscoNXOSPlugin(BasePlugin):
    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            # VRF aware commands
            return [
                f'show ip arp vrf {vrf}',
                f"show ip interface vrf {vrf}",
            ]

        # Standard commands
        return [
            "show cdp neighbors detail",
            "show glbp",
            "show hostname",
            "show hsrp all",
            "show interface switchport",
            "show interface trunk",
            "show interface",
            "show inventory",
            "show ip bgp neighbors",
            "show ip eigrp neighbors",
            "show ip ospf neighbor",
            "show ip route vrf all",
            "show lldp neighbors detail",
            # "show logging",
            "show mac address-table dynamic",
            "show port-channel summary",
            "show running-config",
            "show spanning-tree",
            "show vdc",
            "show version",
            "show vlan",
            "show vpc",
            "show vrf",
            "show vrrp",
        ]

    def collect(self, task: Task) -> dict[str, str]:
        host = task.host
        netmiko_device_type = host.data.get('netmiko_device_type')
        raw_outputs: dict[str, str] = {}
        parsed_outputs: dict[str, list] = {}

        try:
            # Running Standard commands
            for cmd in self.commands():
                raw_output, parsed_output = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                raw_outputs[cmd] = raw_output
                if parsed_output:
                    parsed_outputs[cmd] = parsed_output

            # Running VRF aware commands
            vrfs = ['default'] + [vrf['name'] for vrf in parsed_outputs.get('show vrf', [])]
            for vrf in vrfs:
                for cmd in self.commands(vrf=vrf):
                    raw_output, parsed_output = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                    raw_outputs[cmd] = raw_output

        except Exception:
            logging.error(f"Stopping collection on {self.host_name} due to error")
        return raw_outputs
