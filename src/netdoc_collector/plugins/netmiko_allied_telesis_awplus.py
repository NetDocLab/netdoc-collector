"""Netmiko plugin for Allied Telesis AW+ devices."""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoAlliedTelesisAwplusPlugin(BasePlugin):
    """Netmiko plugin for Allied Telesis AW+ devices."""

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
            logging.error('Stopping collection on %s due to error', self.host_name)

        # Return raw_payload
        if not raw_payload:
            raise RuntimeError(f'No data collected for host {host.name}')
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
