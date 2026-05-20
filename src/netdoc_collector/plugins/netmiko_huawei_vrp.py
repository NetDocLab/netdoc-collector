"""
Plugin for Huawei VRP devices.
"""

import logging
from nornir.core.task import Task
from .base import BasePlugin


class NetmikoHuaweiVRPPlugin(BasePlugin):
    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            # VRF aware commands
            if vrf == 'default':
                # Default VRF is blank
                return [
                    "display ip routing-table verbose",
                ]
            return [
                f"display ip routing-table vpn-instance {vrf} verbose",
            ]

        # Standard commands
        return [
            "display current-configuration | include sysname",
            "display current-configuration",
            "display device manufacture-info",
            "display lldp neighbor",
            "display ip vpn-instance",
            "display interface",
            "display ip vpn-instance interface",
            "display eth-trunk",
            "display ip interface",
            "display vlan all",
            "display lldp neighbor brief",
            "display arp all",
            "display mac-address",
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
