"""Netmiko plugin for Cisco NX-OS devices."""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoCiscoNxosPlugin(BasePlugin):
    """Netmiko plugin for Cisco NX-OS devices."""

    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            # VRF aware commands
            return [
                f'show ip arp vrf {vrf}',
            ]

        # Standard commands
        return [
            'show cdp neighbors detail',
            'show fabricpath route',
            'show glbp',
            'show hostname',
            'show hsrp all',
            'show interface status',
            'show interface switchport',
            'show interface trunk',
            'show interface',
            'show inventory',
            'show ip bgp neighbors',
            'show ip eigrp neighbors',
            'show ip interface vrf all',
            'show ip ospf neighbor',
            'show ip route vrf all',
            'show lacp neighbor',
            'show lldp neighbors detail',
            # "show logging",
            'show mac address-table dynamic',
            'show port-channel summary',
            'show running-config',
            'show spanning-tree',
            'show spanning-tree root',
            'show spanning-tree detail',
            'show spanning-tree summary',
            'show vdc',
            'show version',
            'show vlan',
            'show vdc current-vdc',
            'show vpc',
            'show vpc role',
            'show vrf detail',
            'show vrrp',
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
            vrfs = ['default'] + [vrf['name'] for vrf in parsed_payload.get('show vrf detail', [])]
            for vrf in vrfs:
                for cmd in self.commands(vrf=vrf):
                    raw_text, parsed_text = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                    raw_payload[cmd] = raw_text
                    if parsed_text:
                        parsed_payload[cmd] = parsed_text

        except Exception:
            logging.error('Stopping collection on %s due to error', self.host_name)

        # Return raw_payload
        if not raw_payload:
            raise RuntimeError(f'No data collected for host {host.name}')
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
