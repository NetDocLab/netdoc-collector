"""
Plugin for Cisco XR devices.
"""

import logging
from nornir.core.task import Task
from .base import BasePlugin


class NetmikoCiscoXRPlugin(BasePlugin):
    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            # VRF aware commands
            if vrf == 'default':
                # Default VRF is blank
                return [
                    "show arp",
                    "show route connected",
                    "show route static",
                    "show route rip",
                    "show route bgp",
                    "show route eigrp",
                    "show route ospf",
                    "show route isis",
                ]
            return [
                f"show arp vrf {vrf}",
                f"show route vrf {vrf}",
            ]

        # Standard commands
        return [
            "admin show inventory",
            "show bgp neighbors",
            "show bgp summary",
            "show cdp neighbors detail",
            "show eigrp neighbors",
            "show hsrp",
            "show interfaces",
            "show inventory",
            "show ipv4 vrf all interface",
            "show lldp neighbors",
            "show ospf neighbor",
            "show running-config | include hostname",
            "show running-config",
            "show vrf all detail",
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
