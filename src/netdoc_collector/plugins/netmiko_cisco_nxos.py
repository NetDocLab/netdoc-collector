"""Netmiko plugin for Cisco NX-OS devices."""

import logging

from nornir.core.task import Task

from .base import BasePlugin

class NetmikoCiscoNxosPlugin(BasePlugin):
    """Netmiko plugin for Cisco NX-OS devices."""


    AAA_AUTH_ERROR_MESSAGE ="AAA authorization failed"

    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            # VRF aware commands
            return [
                f'show ip arp vrf {vrf}',
                f'show ip bgp neighbors vrf {vrf}',
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
            'show ip eigrp neighbors',
            'show ip interface vrf all',
            'show ip ospf neighbor vrf all',
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

                retries = 0
                while retries < self.max_retries:
                    raw_output, parsed_output = self.run_netmiko_cmd(task, netmiko_device_type, cmd)

                    if raw_output is not None and self.AAA_AUTH_ERROR_MESSAGE not in raw_output:

                        raw_payload[cmd] = raw_output
                        if parsed_output:
                            parsed_payload[cmd] = parsed_output
                        break
                    logging.error('Retrying command %s on %s due to AAA authorization error', cmd, self.host_name)
                    retries += 1

            # Running VRF aware commands
            vrfs = ['default'] + [vrf['name'] for vrf in parsed_payload.get('show vrf detail', [])]
            for vrf in vrfs:
                for cmd in self.commands(vrf=vrf):

                    retries = 0
                    while retries < self.max_retries:
                        raw_output, parsed_text = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                        if raw_output is not None and self.AAA_AUTH_ERROR_MESSAGE not in raw_output:
                            raw_payload[cmd] = raw_output
                            if parsed_text:
                                parsed_payload[cmd] = parsed_text
                            break
                        logging.error('Retrying command %s on %s due to AAA authorization error', cmd, self.host_name)
                        retries += 1

        except Exception:
            logging.error('Stopping collection on %s due to error', self.host_name)

        # Return raw_payload
        if not raw_payload:
            raise RuntimeError(f'No data collected for host {host.name}')
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
