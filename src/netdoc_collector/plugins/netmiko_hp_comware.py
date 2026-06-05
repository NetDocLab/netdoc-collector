"""
Plugin for HP Comware devices.
"""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoHpComwarePlugin(BasePlugin):
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
            ('display current-configuration | include sysname', 'HOSTNAME'),
            ('display current-configuration', None),
            # Depending on version, "brief" may be unsupportted
            ('display vlan brief', None),
            ('display vlan all', None),
            # Depending on version, "verbose" may be unsupportted
            ('display lldp neighbor-information verbose', None),
            ('display lldp neighbor-information list', None),
            ('display ip vpn-instance', None),
            ('display interface', None),
            ('display ip interface', None),
            ('display mac-address', None),
            ('display link-aggregation verbose', None),
            ('display_device_manuinfo', None),
            # Unsupported
            ('display version', None),
            ('display logbuffer level 6', None),
            ('display stp', None),
            ('display port trunk', None),
            ('display vrrp', None),
            ('display ospf peer', None),
            ('display bgp peer', None),
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
