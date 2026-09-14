"""Netmiko plugin for Cisco WLC (IOS) devices."""

import logging

from nornir.core.task import Task

from .base import BasePlugin


class NetmikoCiscoWlcIosPlugin(BasePlugin):
    """Netmiko plugin for Cisco WLC (IOS) devices."""

    @staticmethod
    def commands() -> list[str]:
        # Standard commands
        return [
            'show ap cdp neighbors',
            'show ap config general',
            'show ap image',
            'show ap summary',
            'show boot',
            'show cdp neighbors detail',
            'show environment summary',
            'show install active',
            'show interface summary',
            'show inventory',
            'show platform',
            'show redundancy states',
            'show redundancy',
            'show running-config all',
            'show version',
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

        except Exception:
            logging.error('Stopping collection on %s due to error', self.host_name)

        # Return raw_payload
        if not raw_payload:
            raise RuntimeError(f'No data collected for host {host.name}')
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
