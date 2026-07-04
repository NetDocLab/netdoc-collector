"""
Plugin for HP Comware devices.
"""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoHpComwarePlugin(BasePlugin):
    """Vendor plugin class for NetmikoHpComwarePlugin."""

    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            # VRF aware commands
            return [
                f'display arp vpn-instance {vrf}',
                f'display ip vpn-instance instance-name {vrf}',
                f'display ip routing-table vpn-instance {vrf}',
            ]

        # Standard commands
        return [
            'display current-configuration',
            # Depending on version, "brief" may be unsupportted
            'display vlan brief',
            'display vlan all',
            # Depending on version, "verbose" may be unsupportted
            'display lldp neighbor-information verbose',
            'display lldp neighbor-information list',
            'display ip vpn-instance',
            'display interface',
            'display ip interface',
            'display mac-address',
            'display link-aggregation verbose',
            'display_device_manuinfo',
            # Unsupported
            'display version',
            'display logbuffer level 6',
            'display stp',
            'display port trunk',
            'display vrrp',
            'display ospf peer',
            'display bgp peer',
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

        # Return raw_payload
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
