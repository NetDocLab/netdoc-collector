"""
Plugin for Cisco IOS / IOS-XE devices.
"""

from typing import Any
from nornir.core.task import Task
from .base import BasePlugin


class NetmikoCiscoIOSPlugin(BasePlugin):
    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            # VRF aware commands
            if vrf == 'default':
                # Default VRF is blank
                return [
                    'show ip arp',
                    'show ip route',
                ]
            return [
                f'show ip arp vrf {vrf}',
                f'show ip route vrf {vrf}',
            ]

        # Standard commands
        return [
            # "show version", "HOSTNAME"),
            'show authentication sessions',
            'show cdp neighbors detail',
            'show device-tracking database',
            'show dot1x all',
            'show etherchannel summary',
            'show glbp',
            'show interfaces status',
            'show interfaces switchport',
            'show interfaces trunk',
            'show interfaces',
            'show inventory',
            'show ip bgp neighbors',
            'show ip eigrp neighbors',
            'show ip interface',
            'show ip ospf neighbor',
            'show isis neighbors',
            'show lldp neighbors detail',
            'show logging last 200',
            'show mac address-table dynamic',
            'show running-config',
            'show spanning-tree',
            'show standby',
            'show switch',
            'show version',
            'show vlan',
            'show vrf',
            'show vrrp all',
        ]

    def collect(self, task: Task) -> dict[str, str]:
        host = task.host
        errors = []
        netmiko_device_type = host.data.get('netmiko_device_type')
        raw_outputs: dict[str, str] = {}
        parsed_outputs: dict[str, list] = {}

        # Running Standard commands
        for cmd in self.commands():
            raw_output, parsed_output, cmd_errors = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
            errors = errors + cmd_errors
            raw_outputs[cmd] = raw_output
            if parsed_output:
                parsed_outputs[cmd] = parsed_output

        # Running VRF aware commands
        vrfs = ['default'] + [vrf['name'] for vrf in parsed_outputs.get('show vrf', [])]
        for vrf in vrfs:
            for cmd in self.commands(vrf=vrf):
                raw_output, parsed_output, errors = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                errors = errors + cmd_errors
                raw_outputs[cmd] = raw_output

        # Upload
        upload_errors = self.upload_raw_outputs(raw_outputs)
        errors = errors + upload_errors

        return errors
