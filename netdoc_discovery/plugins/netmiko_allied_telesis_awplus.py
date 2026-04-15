from typing import Any
from nornir.core.task import Task
from .base import BasePlugin

# TODO: not tested


class NetmikoAlliedTelesisAwplusPlugin(BasePlugin):
    @staticmethod
    def commands() -> list[str]:
        # Standard commands
        return [
            "show system",
            "show running-config",
            "show system",
            "show vlan all",
            "show interface",
            "show interface switchport",
            "show static-channel-group",
            "show etherchannel summary",
            "show lldp neighbors detail",
            "show ip route",
            "show arp",
            "show mac address-table",
            # Unsupported
            "show ip interface",
            "show ip vrf detail",
            "show ip vrf interface",
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
            iface_mtu = iface_data.get('mac_address')
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

        # Convert to NetDoc format
        netdoc_output = self.to_netdoc_dict(parsed_outputs)
        self.write_output(netdoc_output, 'netdoc-device-report')

        return netdoc_output
