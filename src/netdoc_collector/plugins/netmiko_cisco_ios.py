"""Netmiko plugin for Cisco IOS devices."""

import logging
import re

from nornir.core.task import Task

from .base import BasePlugin
from .cisco_eigrp import eigrp_configured_vrfs, ios_eigrp_commands
from .cisco_isis import ios_isis_commands, ios_isis_processes

_CATALYST_9500 = re.compile(r'C9500-[A-Z0-9]+(?:-[A-Z0-9]+)*', re.I)
_IOS_XE_17_3 = re.compile(r'17\.0?3\.[0-9]+[a-z]?', re.I)


def _supports_system_mtu(version_rows) -> bool:
    for row in version_rows:
        hardware = row.get('hardware')
        if (
            isinstance(hardware, list)
            and _IOS_XE_17_3.fullmatch(str(row.get('version', '')))
            and any(_CATALYST_9500.fullmatch(str(model)) for model in hardware)
        ):
            return True
    return False


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
            'show vrrp detail',
            'show vtp status',
            'show wlan sum',
        ]

    def collect(self, task: Task) -> dict[str, dict]:
        host = task.host
        netmiko_device_type = host.data.get('netmiko_device_type')
        raw_payload: dict[str, str] = {}
        parsed_payload: dict[str, list] = {}

        def run_commands(commands):
            for cmd in commands:
                for _ in range(self.max_retries):
                    raw, parsed = self.run_netmiko_cmd(task, netmiko_device_type, cmd)
                    if raw is not None and self.AAA_AUTH_ERROR_MESSAGE not in raw:
                        raw_payload[cmd] = raw
                        if parsed:
                            parsed_payload[cmd] = parsed
                        break
                    logging.error(
                        'Retrying command %s on %s due to AAA authorization error',
                        cmd,
                        self.host_name,
                    )

        try:
            run_commands(self.commands())

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
                run_commands(self.commands(vrf=vrf, config=config))

            if _supports_system_mtu(parsed_payload.get('show version', [])):
                run_commands(['show system mtu'])

        except Exception:
            logging.error('Stopping collection on %s due to error', self.host_name)

        # Return raw_payload
        if not raw_payload:
            raise RuntimeError(f'No data collected for host {host.name}')
        return {'raw_outputs': raw_payload, 'parsed_outputs': parsed_payload}
