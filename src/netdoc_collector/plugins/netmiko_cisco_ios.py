"""Netmiko plugin for Cisco IOS devices."""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoCiscoIosPlugin(BasePlugin):
    """Netmiko plugin for Cisco IOS devices."""

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
            'show aaa servers detailed',
            'show aaa servers',
            'show ap cdp neighbors',
            'show ap config general',
            'show ap image',
            'show ap summary',
            'show authentication sessions',
            'show boot',
            'show cdp neighbors detail',
            'show device-tracking database',
            'show dot1x all',
            'show environment fan',
            'show environment power all',
            'show environment summary',
            'show environment temperature',
            'show errdisable detect',
            'show errdisable recovery',
            'show etherchannel summary',
            'show glbp',
            'show install active',
            'show interface summary',
            'show interfaces status err-disabled',
            'show interfaces status',
            'show interfaces switchport',
            'show interfaces trunk',
            'show interfaces',
            'show inventory',
            'show ip bgp neighbors',
            'show ip eigrp neighbors',
            'show ip interface',
            'show ip ospf neighbor',
            'show ip ssh',
            'show isis neighbors',
            'show license status',
            'show license summary',
            'show lldp neighbors detail',
            'show logging last 200',
            'show mac address-table dynamic',
            'show ntp associations',
            'show platform',
            'show radius server-group all',
            'show redundancy states',
            'show redundancy',
            'show running-config',
            'show spanning-tree root',
            'show spanning-tree summary',
            'show spanning-tree',
            'show standby',
            'show switch stack-ports',
            'show switch',
            'show version',
            'show vlan',
            'show vrf',
            'show vrrp all',
            'show vtp status',
            'show wlan sum',
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
            logging.error('Stopping collection on %s due to error', self.host_name)

        # Return raw_payload
        if not raw_payload:
            raise RuntimeError(f'No data collected for host {host.name}')
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
