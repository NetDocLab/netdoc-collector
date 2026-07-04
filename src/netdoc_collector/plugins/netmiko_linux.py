"""
Plugin for Linux devices.
"""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoLinuxAnyPlugin(BasePlugin):
    """Vendor plugin class for NetmikoLinuxAnyPlugin."""

    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            # VRF aware commands
            if vrf == 'default':
                # Default VRF is blank
                return [
                    'show ip arp',
                    'ip route show',
                ]
            return [
                f'show ip arp vrf {vrf}',
                f'ip route show table {vrf}',
            ]

        # Standard commands
        return [
            'hostname',
            'ip link show',
            'ip address show',
            'ip vrf show',
            # "arp -an",
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

            # Running VRF aware commands
            vrfs = ['default'] + [vrf['name'] for vrf in parsed_payload.get('show vrf', [])]
            for vrf in vrfs:
                for cmd in self.commands(vrf=vrf):
                    raw_text, parsed_text = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                    raw_payload[cmd] = raw_text
                    if parsed_text:
                        parsed_payload[cmd] = parsed_text

        except Exception:
            logging.error(f'Stopping collection on {self.host_name} due to error')

        # Return raw_payload
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
