"""Netmiko plugin for Cisco NX-OS devices."""

import logging
import re

from nornir.core.task import Task

from .base import BasePlugin


def _bgp_template_commands(config: str, vrf: str) -> list[str]:
    commands = {}
    scope, vrf_indent, in_bgp = 'default', None, False
    for line in config.splitlines():
        item = line.strip()
        if not item or item.startswith('!'):
            continue
        indent = len(line) - len(line.lstrip())
        if not indent:
            in_bgp = bool(re.fullmatch(r'router bgp [\d.]+', item))
            scope, vrf_indent = 'default', None
        if not in_bgp:
            continue
        if vrf_indent is not None and indent <= vrf_indent:
            scope, vrf_indent = 'default', None
        if match := re.fullmatch(r'vrf ([\w.:-]+)', item, re.ASCII):
            scope, vrf_indent = match[1], indent
            continue
        template = re.fullmatch(
            r'template (peer|peer-session|peer-policy) ([\w.:-]+)', item, re.ASCII
        )
        if template and scope == vrf:
            family = 'peer-template' if template[1] == 'peer' else template[1]
            suffix = '' if vrf == 'default' else f' vrf {vrf}'
            commands[f'show bgp {family} {template[2]}{suffix}'] = None
    return list(commands)


class NetmikoCiscoNxosPlugin(BasePlugin):
    """Netmiko plugin for Cisco NX-OS devices."""

    AAA_AUTH_ERROR_MESSAGE = 'AAA authorization failed'

    @staticmethod
    def commands(vrf=None, *, config='') -> list[str]:
        if vrf:
            # VRF aware commands
            return [
                f'show ip arp vrf {vrf}',
                f'show ip bgp neighbors vrf {vrf}',
                f'show bgp vrf {vrf} all neighbors',
                f'show ip ospf vrf {vrf}',
                f'show ip ospf interface vrf {vrf}',
                *_bgp_template_commands(config, vrf),
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
            'show ipv6 interface vrf all',
            'show ipv6 neighbor vrf all',
            'show ipv6 route vrf all',
            'show ospfv3 vrf all | json',
            'show ospfv3 interface vrf all | json',
            'show ospfv3 neighbors detail vrf all | json',
            'show ospfv3 virtual-links vrf all | json',
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
            # VXLAN commands
            'show nve interface',
            'show nve peers',
            'show nve vni',
            'show l2route evpn mac all',
            'show l2route evpn mac-ip all',
            'show vxlan',  # mapping VLAN ID - VNI
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
                    logging.error(
                        'Retrying command %s on %s due to AAA authorization error',
                        cmd,
                        self.host_name,
                    )
                    retries += 1

            # Running VRF aware commands
            vrfs = []
            seen_vrfs = set()
            for row in parsed_payload.get('show vrf detail', []):
                name = str(row.get('name', '')).strip()
                key = name
                if name and key not in seen_vrfs:
                    seen_vrfs.add(key)
                    vrfs.append(name)
            if 'default' not in seen_vrfs:
                vrfs.insert(0, 'default')
            for vrf in vrfs:
                for cmd in self.commands(
                    vrf=vrf, config=raw_payload.get('show running-config', '')
                ):
                    retries = 0
                    while retries < self.max_retries:
                        raw_output, parsed_text = self.run_netmiko_cmd(
                            task, netmiko_device_type, cmd
                        )
                        if raw_output is not None and self.AAA_AUTH_ERROR_MESSAGE not in raw_output:
                            raw_payload[cmd] = raw_output
                            if parsed_text:
                                parsed_payload[cmd] = parsed_text
                            break
                        logging.error(
                            'Retrying command %s on %s due to AAA authorization error',
                            cmd,
                            self.host_name,
                        )
                        retries += 1

        except Exception:
            logging.error('Stopping collection on %s due to error', self.host_name)

        # Return raw_payload
        if not raw_payload:
            raise RuntimeError(f'No data collected for host {host.name}')
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
