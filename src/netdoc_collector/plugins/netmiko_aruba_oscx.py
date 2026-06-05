"""
Plugin for Aruba OSCX devices.
"""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoArubaOscxPlugin(BasePlugin):
    """Vendor plugin class for NetmikoArubaOscxPlugin."""

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
            'show system',
            'show running-config',
            'show vlan',
            'show interface',
            'show lldp neighbor-info detail',
            'show mac-address-table',
            'show arp all-vrfs',
            'show ip interface brief',
            'show ip route all-vrfs',
            # Unsupported
            'show vrf',
            'show cdp neighbor-info',
            'show lag',
            'show version',
            'show logging',
            'show spanning-tree',
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
            logging.error(f'Stopping collection on {self.host_name} due to error')
        return raw_outputs
