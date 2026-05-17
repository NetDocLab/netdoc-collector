import re
from ipaddress import ip_network
from typing import Any

from nornir.core.task import Task
from netdoc_sdk.models import (
    # ARPEntryData,
    # DeviceData,
    RawOutput,
    # InterfaceData,
    # InterfaceMode,
    # InterfaceType,
    # IPAddressData,
    # LLDPNeighborData,
    # MACEntryData,
    # RouteData,
    # RouteProtocol,
    # VLANData,
    # VRFData,
)

from .base import BasePlugin


class NetmikoCiscoNXOSPlugin(BasePlugin):
    @staticmethod
    def commands(vrf=None) -> list[str]:
        if vrf:
            return [
                f'show ip arp vrf {vrf}',
                f"show ip interface vrf {vrf}",
            ]

        # Standard commands
        return [
            "show cdp neighbors detail",
            "show glbp",
            "show hostname",
            "show hsrp all",
            "show interface switchport",
            "show interface trunk",
            "show interface",
            "show inventory",
            "show ip bgp neighbors",
            "show ip eigrp neighbors",
            "show ip ospf neighbor",
            "show ip route vrf all",
            "show lldp neighbors detail",
            # "show logging",
            "show mac address-table dynamic",
            "show port-channel summary",
            "show running-config",
            "show spanning-tree",
            "show vdc",
            "show version",
            "show vlan",
            "show vpc",
            "show vrf",
            "show vrrp",
        ]

    @staticmethod
    def to_netdoc_dict(parsed_outputs: dict[str, list]) -> dict[str, Any]:
        netdoc_output = {}
        device_interfaces = []

        # Parse device ID (hostname, fqdn, serial)
        show_version = parsed_outputs.get('show version', [{}])[0]
        hostname = show_version.get('hostname')
        serial = show_version.get('serial')
        if hostname:
            netdoc_output['hostname'] = hostname
        if serial:
            netdoc_output['serial'] = serial

        # Parse interfaces
        show_interfaces = parsed_outputs.get('show interfaces', [])
        for iface_data in show_interfaces:
            iface_name = iface_data.get('interface')
            iface_description = iface_data.get('description')
            iface_status = iface_data.get('link_status')
            iface_type = iface_data.get('hardware_type')
            iface_mac_address = iface_data.get('mac_address')
            iface_mtu = iface_data.get('mtu')
            iface_bandwidth = iface_data.get('bandwidth')
            iface_input_packets = iface_data.get('input_packets')
            iface_output_packets = iface_data.get('output_packets')
            iface_input_errors = iface_data.get('input_errors')
            iface_output_errors = iface_data.get('output_errors')
            device_interfaces.append(
                {
                    'name': iface_name,
                    'description': iface_description,
                    'status': iface_status,
                    'type': iface_type,
                    'mac_address': iface_mac_address,
                    'mtu': iface_mtu,
                    'bandwidth': iface_bandwidth,
                    'input_packets': iface_input_packets,
                    'input_errors': iface_input_errors,
                    'output_packets': iface_output_packets,
                    'output_errors': iface_output_errors,
                }
            )
        netdoc_output['interfaces'] = device_interfaces

        return netdoc_output

    # @staticmethod
    # def _interface_type(name: str, hardware_type: str = '') -> InterfaceType:
    #     interface_name = name.lower()
    #     hardware = hardware_type.lower()

    #     if interface_name.startswith('mgmt'):
    #         return InterfaceType.MANAGEMENT
    #     if interface_name.startswith('loopback'):
    #         return InterfaceType.LOOPBACK
    #     if interface_name.startswith('vlan'):
    #         return InterfaceType.VLAN
    #     if interface_name.startswith('port-channel') or re.match(r'^po\d+', interface_name):
    #         return InterfaceType.PORT_CHANNEL
    #     if interface_name.startswith('tunnel') or interface_name.startswith('nve'):
    #         return InterfaceType.TUNNEL
    #     if interface_name.startswith(('ethernet', 'eth')) or 'ethernet' in hardware:
    #         return InterfaceType.ETHERNET
    #     return InterfaceType.OTHER

    # @staticmethod
    # def _interface_mode(
    #     interface_type: InterfaceType,
    #     switchport_data: dict[str, Any],
    #     interface_data: dict[str, Any],
    # ) -> InterfaceMode:
    #     if interface_type == InterfaceType.TUNNEL:
    #         return InterfaceMode.TUNNEL

    #     switchport = str(switchport_data.get('switchport', '')).lower()
    #     mode = str(switchport_data.get('mode') or interface_data.get('mode') or '').lower()

    #     if switchport == 'disabled' or 'routed' in mode:
    #         return InterfaceMode.ROUTED
    #     if 'trunk' in mode:
    #         return InterfaceMode.TRUNK
    #     return InterfaceMode.ACCESS

    # @staticmethod
    # def _route_protocol(protocol: Any) -> RouteProtocol:
    #     protocol_text = str(protocol or '').lower()

    #     if protocol_text in {'direct', 'local', 'connected'}:
    #         return RouteProtocol.CONNECTED
    #     if 'bgp' in protocol_text:
    #         return RouteProtocol.BGP
    #     if 'ospf' in protocol_text:
    #         return RouteProtocol.OSPF
    #     if 'eigrp' in protocol_text:
    #         return RouteProtocol.EIGRP
    #     if protocol_text == 'rip':
    #         return RouteProtocol.RIP
    #     if 'isis' in protocol_text or 'is-is' in protocol_text:
    #         return RouteProtocol.ISIS
    #     if protocol_text == 'static':
    #         return RouteProtocol.STATIC
    #     return RouteProtocol.OTHER

    # @classmethod
    # def _cidr_address(cls, ip_address: Any, subnet: Any = '', prefix: Any = '') -> str:
    #     if not ip_address:
    #         return ''

    #     address = str(ip_address).strip()
    #     if not address:
    #         return ''
    #     if '/' in address:
    #         return address

    #     prefix_length = cls.safe_int(prefix)
    #     if prefix_length is None and subnet:
    #         try:
    #             prefix_length = ip_network(str(subnet).strip(), strict=False).prefixlen
    #         except ValueError:
    #             prefix_length = None

    #     if prefix_length is None:
    #         return address
    #     return f'{address}/{prefix_length}'

    # @staticmethod
    # def _vrf_from_command(command: str) -> str:
    #     match = re.search(r'\bvrf\s+(.+)$', command)
    #     if not match:
    #         return ''
    #     return match.group(1).strip()

    # @staticmethod
    # def _capabilities(value: Any) -> list[str]:
    #     if isinstance(value, list):
    #         return [str(item).strip() for item in value if str(item).strip()]
    #     if not value:
    #         return []
    #     return [item for item in re.split(r'[\s,]+', str(value).strip()) if item]

    # @staticmethod
    # def _tag_to_int(value: Any) -> int | None:
    #     if not value:
    #         return None
    #     match = re.search(r'\d+', str(value))
    #     if not match:
    #         return None
    #     return int(match.group(0))

    def to_netdok_obj(
        self,
        parsed_outputs: dict[str, Any],
        raw_outputs: dict[str, str] | None = None,
    ) -> RawOutput:
        """Convert parsed NX-OS outputs to a DeviceData object for persistence."""
        parsed_outputs = parsed_outputs or {}
        raw_outputs = raw_outputs if isinstance(raw_outputs, dict) else {}

        show_version = self.first_record(parsed_outputs.get('show version'))
        show_hostname = self.first_record(parsed_outputs.get('show hostname'))
        inventory = parsed_outputs.get('show inventory', [])
        chassis = next(
            (item for item in inventory if isinstance(item, dict) and str(item.get('name', '')).lower() == 'chassis'),
            {},
        )

        hostname = show_version.get('hostname') or show_hostname.get('hostname') or self.host_name or 'unknown'
        model = chassis.get('pid') or show_version.get('platform') or ''
        serial_number = show_version.get('serial') or chassis.get('sn') or ''

        # VLANs
        vlans: list[VLANData] = []
        for vlan_data in parsed_outputs.get('show vlan', []):
            vlan_id = self.safe_int(vlan_data.get('vlan_id'))
            if vlan_id is None:
                continue
            vlan = self.safe_model(
                VLANData,
                vlan_id=vlan_id,
                name=vlan_data.get('vlan_name') or '',
                state=vlan_data.get('status') or 'active',
            )
            if vlan:
                vlans.append(vlan)

        # VRFs
        vrfs: list[VRFData] = []
        for vrf_data in parsed_outputs.get('show vrf', []):
            vrf_name = vrf_data.get('name')
            if not vrf_name:
                continue
            vrf = self.safe_model(
                VRFData,
                name=vrf_name,
                description=vrf_data.get('reason') or '',
            )
            if vrf:
                vrfs.append(vrf)

        # Interfaces
        switchports = {
            item.get('interface'): item
            for item in parsed_outputs.get('show interface switchport', [])
            if isinstance(item, dict) and item.get('interface')
        }

        interfaces: list[InterfaceData] = []
        interface_names: set[str] = set()
        for interface_data in parsed_outputs.get('show interface', []):
            interface_name = interface_data.get('interface')
            if not interface_name:
                continue

            switchport_data = switchports.get(interface_name, {})
            interface_type = self._interface_type(
                interface_name,
                interface_data.get('hardware_type') or '',
            )
            mode = self._interface_mode(
                interface_type,
                switchport_data,
                interface_data,
            )
            link_status = str(interface_data.get('link_status') or '').lower()
            admin_state = str(interface_data.get('admin_state') or '').lower()
            admin_status = 'down' if 'administratively down' in link_status else admin_state or 'up'
            oper_status = 'up' if link_status.startswith('up') else 'down' if link_status else 'up'

            access_vlan_id = self.safe_int(switchport_data.get('access_vlan'))
            native_vlan_id = self.safe_int(switchport_data.get('native_vlan'))
            if mode == InterfaceMode.ACCESS:
                native_vlan_id = access_vlan_id or native_vlan_id
                allowed_vlan_ids = [native_vlan_id] if native_vlan_id else []
            elif mode == InterfaceMode.TRUNK:
                allowed_vlan_ids = self.expand_vlan_ids(switchport_data.get('trunking_vlans'))
            else:
                native_vlan_id = None
                allowed_vlan_ids = []

            interface = self.safe_model(
                InterfaceData,
                name=interface_name,
                description=interface_data.get('description') or '',
                admin_status=admin_status,
                oper_status=oper_status,
                speed_mbps=self._speed_to_mbps(
                    interface_data.get('speed'),
                    interface_data.get('bandwidth'),
                ),
                mtu=self.safe_int(interface_data.get('mtu'), 1500) or 1500,
                mac_address=interface_data.get('mac_address') or '',
                interface_type=interface_type,
                mode=mode,
                native_vlan_id=native_vlan_id,
                allowed_vlan_ids=allowed_vlan_ids,
            )
            if interface:
                interfaces.append(interface)
                interface_names.add(interface_name)

        # IP Addresses
        ip_addresses: list[IPAddressData] = []
        seen_ip_addresses: set[tuple[str, str, str, bool]] = set()

        def add_ip_address(
            interface_name: str,
            address: str,
            vrf_name: str = '',
            is_secondary: bool = False,
        ) -> None:
            if not interface_name or not address:
                return
            key = (interface_name, address, vrf_name, is_secondary)
            if key in seen_ip_addresses:
                return
            ip_address = self.safe_model(
                IPAddressData,
                interface_name=interface_name,
                address=address,
                vrf_name=vrf_name,
                is_secondary=is_secondary,
            )
            if ip_address:
                ip_addresses.append(ip_address)
                seen_ip_addresses.add(key)

        # Collecting IP addresses from "show ip interface" outputs
        for command, command_output in parsed_outputs.items():
            if not command.startswith('show ip interface'):
                continue

            command_vrf = self._vrf_from_command(command)
            for interface_data in command_output:
                interface_name = interface_data.get('interface') or ''
                if interface_name and interface_name not in interface_names:
                    interface = self.safe_model(
                        InterfaceData,
                        name=interface_name,
                        admin_status=interface_data.get('admin_status') or 'up',
                        oper_status=interface_data.get('link_status') or 'up',
                        mtu=self.safe_int(interface_data.get('mtu'), 1500) or 1500,
                        interface_type=self._interface_type(interface_name),
                        mode=InterfaceMode.ROUTED,
                    )
                    if interface:
                        interfaces.append(interface)
                        interface_names.add(interface_name)

                vrf_name = interface_data.get('vrf_name') or command_vrf
                primary_address = self._cidr_address(
                    interface_data.get('primary_ip_address'),
                    subnet=interface_data.get('primary_ip_subnet'),
                )
                add_ip_address(interface_name, primary_address, vrf_name)

                secondary_addresses = interface_data.get('secondary_ip_address') or []
                secondary_subnets = interface_data.get('secondary_ip_subnet') or []
                for index, secondary_address in enumerate(secondary_addresses):
                    secondary_subnet = secondary_subnets[index] if index < len(secondary_subnets) else ''
                    address = self._cidr_address(
                        secondary_address,
                        subnet=secondary_subnet,
                    )
                    add_ip_address(interface_name, address, vrf_name, True)

        for interface_data in parsed_outputs.get('show interface', []):
            interface_name = interface_data.get('interface') or ''
            address = self._cidr_address(
                interface_data.get('ip_address'),
                prefix=interface_data.get('prefix_length'),
            )
            if not address:
                continue
            has_address = any(
                item.interface_name == interface_name and item.address == address for item in ip_addresses
            )
            if not has_address:
                add_ip_address(interface_name, address)

        # Routes
        routes: list[RouteData] = []
        for route_data in parsed_outputs.get('show ip route vrf all', []):
            network = route_data.get('network')
            prefix_length = route_data.get('prefix_length')
            next_hop = route_data.get('nexthop_ip') or route_data.get('nexthop_if')
            if not network or not prefix_length or not next_hop:
                continue

            route = self.safe_model(
                RouteData,
                prefix=f'{network}/{prefix_length}',
                next_hop=next_hop,
                protocol=self._route_protocol(route_data.get('protocol')),
                vrf_name=route_data.get('vrf') or '',
                metric=self.safe_int(route_data.get('metric'), 0) or 0,
                preference=self.safe_int(route_data.get('distance'), 0) or 0,
                next_hop_interface=route_data.get('nexthop_if') or '',
                tag=self._tag_to_int(route_data.get('tag')),
                leaked_from_vrf=route_data.get('nexthop_vrf') or '',
            )
            if route:
                routes.append(route)

        # ARP entries
        arp_entries: list[ARPEntryData] = []
        for command, command_output in parsed_outputs.items():
            if not command.startswith('show ip arp'):
                continue

            vrf_name = self._vrf_from_command(command)
            for arp_data in command_output:
                if not (arp_data.get('ip_address') and arp_data.get('mac_address') and arp_data.get('interface')):
                    continue
                arp_entry = self.safe_model(
                    ARPEntryData,
                    ip_address=arp_data.get('ip_address') or '',
                    mac_address=arp_data.get('mac_address') or '',
                    interface_name=arp_data.get('interface') or '',
                    vrf_name=vrf_name,
                )
                if arp_entry:
                    arp_entries.append(arp_entry)

        # MAC address table entries
        mac_entries: list[MACEntryData] = []
        for mac_data in parsed_outputs.get('show mac address-table dynamic', []):
            vlan_id = self.safe_int(mac_data.get('vlan_id'))
            if vlan_id is None or not mac_data.get('mac_address'):
                continue

            ports = [port.strip() for port in str(mac_data.get('ports') or '').split(',') if port.strip()]
            if not ports:
                continue
            for port in ports:
                mac_entry = self.safe_model(
                    MACEntryData,
                    mac_address=mac_data.get('mac_address') or '',
                    vlan_id=vlan_id,
                    interface_name=port,
                    entry_type=mac_data.get('type') or 'dynamic',
                )
                if mac_entry:
                    mac_entries.append(mac_entry)

        # LLDP neighbors
        lldp_neighbors: list[LLDPNeighborData] = []
        for neighbor_data in parsed_outputs.get('show lldp neighbors detail', []):
            if not (
                neighbor_data.get('local_interface')
                and neighbor_data.get('neighbor_name')
                and neighbor_data.get('neighbor_interface')
            ):
                continue
            neighbor = self.safe_model(
                LLDPNeighborData,
                local_interface=neighbor_data.get('local_interface') or '',
                remote_device=neighbor_data.get('neighbor_name') or '',
                remote_interface=neighbor_data.get('neighbor_interface') or '',
                remote_description=neighbor_data.get('neighbor_description') or '',
                capabilities=self._capabilities(neighbor_data.get('capabilities')),
            )
            if neighbor:
                lldp_neighbors.append(neighbor)

        device = self.safe_model(
            DeviceData,
            hostname=hostname,
            vendor='cisco',
            model=model,
            platform='nxos',
            serial_number=serial_number,
            os_version=show_version.get('os') or '',
            uptime_seconds=self._uptime_to_seconds(show_version.get('uptime')),
            mgmt_ip=self.host_data.get('ansible_host') or '',
            site=self.host_data.get('site') or '',
            role=self.host_data.get('role') or '',
            vlans=vlans,
            vrfs=vrfs,
            interfaces=interfaces,
            ip_addresses=ip_addresses,
            routes=routes,
            arp_entries=arp_entries,
            mac_entries=mac_entries,
            lldp_neighbors=lldp_neighbors,
            raw_config=raw_outputs.get('show running-config') or '',
            raw_outputs=raw_outputs,
            parsed_state=parsed_outputs,
        )

        return device or DeviceData(hostname=hostname, vendor='cisco', platform='nxos')

    def collect(self, task: Task) -> dict[str, str]:
        host = task.host
        netmiko_device_type = host.data.get('netmiko_device_type')
        netdoc_output = {}
        raw_outputs: dict[str, str] = {}
        parsed_outputs: dict[str, list] = {}

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
                if parsed_output:
                    parsed_outputs[cmd] = parsed_output

        # Convert to NetDoc format
        netdoc_output = self.to_netdoc_dict(parsed_outputs)

        device = self.to_netdok_obj(parsed_outputs, raw_outputs)
        self.write_output(netdoc_output, 'netdoc-device-report')

        return {"netdoc_output": netdoc_output, "device": device}
