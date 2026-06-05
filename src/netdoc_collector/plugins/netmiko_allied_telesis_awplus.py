"""
Plugin for Allied Telesis AW+ devices.
"""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoAlliedTelesisAwplusPlugin(BasePlugin):
    @staticmethod
    def commands() -> list[str]:
        # Standard commands
        return [
            'show system',
            'show running-config',
            'show system',
            'show vlan all',
            'show interface',
            'show interface switchport',
            'show static-channel-group',
            'show etherchannel summary',
            'show lldp neighbors detail',
            'show ip route',
            'show arp',
            'show mac address-table',
            # Unsupported
            'show ip interface',
            'show ip vrf detail',
            'show ip vrf interface',
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

        except Exception:
            logging.error(f'Stopping collection on {self.host_name} due to error')
        return raw_outputs
