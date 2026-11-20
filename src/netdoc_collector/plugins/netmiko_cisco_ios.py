"""Netmiko plugin for Cisco IOS devices."""

import logging

from nornir.core.task import Task

from .base import BasePlugin
from .cisco_eigrp import eigrp_configured_vrfs, ios_eigrp_commands
from .cisco_isis import ios_isis_commands, ios_isis_processes


class NetmikoCiscoIosPlugin(BasePlugin):
    """Netmiko plugin for Cisco IOS devices."""

    AAA_AUTH_ERROR_MESSAGE = 'AAA authorization failed'

    @staticmethod
    def commands(vrf=None, *, config='') -> list[str]:
        if vrf:
            # VRF aware commands
            if vrf == 'default':
                # Default VRF is blank
                return [
                    'show ip arp',
                    'show ip route',
                    'show ipv6 neighbors',
                    'show ipv6 route',
                    'show ipv6 nd on-link prefix',
                    *ios_eigrp_commands(config, vrf),
                    *ios_isis_commands(config, vrf),
                ]
            return [
                f'show ip arp vrf {vrf}',
                f'show ip bgp vpnv4 vrf {vrf} neighbors',
                f'show ip bgp vpnv6 unicast vrf {vrf} neighbors',
                f'show ip route vrf {vrf}',
                f'show ipv6 neighbors vrf {vrf}',
                f'show ipv6 route vrf {vrf}',
                f'show ipv6 nd on-link prefix vrf {vrf}',
                *ios_eigrp_commands(config, vrf),
                *ios_isis_commands(config, vrf),
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
            'show clns protocol',
            'show clns interface',
            'show clns is-neighbors detail',
            'show isis hostname',
            'show isis neighbors detail',
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
            'show ip bgp template peer-session',
            'show ip bgp template peer-policy',
            'show bgp ipv6 unicast neighbors',
            'show ip eigrp neighbors',
            'show ip eigrp neighbors detail',
            'show ip eigrp interfaces detail',
            'show ipv6 eigrp neighbors detail',
            'show ipv6 eigrp interfaces detail',
            'show ip interface',
            'show ip ospf',
            'show ip ospf neighbor',
            'show ip ospf interface',
            'show ip ssh',
            'show ipv6 interface',
            'show ipv6 ospf',
            'show ipv6 ospf interface',
            'show ipv6 ospf neighbor detail',
            'show ipv6 ospf virtual-links',
            'show ospfv3',
            'show ospfv3 ipv4 interface',
            'show ospfv3 ipv4 neighbor detail',
            'show ospfv3 ipv4 virtual-links',
            'show ospfv3 ipv6 interface',
            'show ospfv3 ipv6 neighbor detail',
            'show ospfv3 ipv6 virtual-links',
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
            'show standby all',
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
            for row in parsed_payload.get('show vrf', []):
                name = str(row.get('name', '')).strip()
                key = name
                if name and key not in seen_vrfs:
                    seen_vrfs.add(key)
                    vrfs.append(name)
            if 'default' not in seen_vrfs:
                vrfs.insert(0, 'default')
            config = raw_payload.get('show running-config', '')
            vrfs.extend(name for name in eigrp_configured_vrfs(config) if name not in vrfs)
            vrfs.extend(name for name in ios_isis_processes(config) if name not in vrfs)
            for vrf in vrfs:
                for cmd in self.commands(vrf=vrf, config=config):
                    retries = 0
                    while retries < self.max_retries:
                        raw_text, parsed_text = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                        if raw_text is not None and self.AAA_AUTH_ERROR_MESSAGE not in raw_text:
                            raw_payload[cmd] = raw_text
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
