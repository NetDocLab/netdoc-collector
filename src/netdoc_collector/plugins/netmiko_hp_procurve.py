"""
Plugin for HP Procurve devices.
"""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoHpProcurvePlugin(BasePlugin):
    """Vendor plugin class for NetmikoHpProcurvePlugin."""

    @staticmethod
    def commands() -> list[str]:
        # Standard commands
        return [
            'show system',
            'show running-config',
            'show vlans',
            'show interfaces brief',
            'show cdp neighbors detail',
            'show lldp info remote-device',
            'show mac-address',
            'show arp',
            'show trunks',
            'show ip',
            'show ip route',
            'show version',
            'show system',
            'show logging',
            'show spanning-tree',
        ]

    def collect(self, task: Task) -> dict[str, dict]:
        host = task.host
        netmiko_device_type = host.data.get('netmiko_device_type')
        raw_payload: dict[str, str] = {}
        parsed_payload: dict[str, list] = {}

        try:
            # Running Standard commands
            for cmd in self.commands():
                raw_output, parsed_output = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                raw_payload[cmd] = raw_output
                if parsed_output:
                    parsed_payload[cmd] = parsed_output

        except Exception:
            logging.error(f'Stopping collection on {self.host_name} due to error')

        return {'raw_output': raw_payload, 'parsed_output': parsed_payload}
