"""Async network scanner and host discovery utilities.

This module implements an asynchronous TCP port scanner that can optionally
probe SSH endpoints with Netmiko to detect device types and map them to
NetDoc plugins.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from ipaddress import IPv4Network
from pathlib import Path
from typing import Any

from netmiko.exceptions import NetmikoAuthenticationException
from netmiko.ssh_autodetect import SSHDetect

logger = logging.getLogger('scanner')


# ─────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────
@dataclass
class HostResult:
    """Result of a single host scan.

    Attributes:
        ip (str): host IP address.
        port (int | None): first responsive port discovered.
        netmiko_device_type (str | None): Netmiko autodetect device type.
        netdoc_plugin (str | None): mapped NetDoc plugin identifier.
        credential (dict[str]): credential record used for probing.
    """

    ip: str
    port: int | None = None
    netmiko_device_type: str | None = None
    netdoc_plugin: str | None = None
    credential: dict[str, str] = field(default_factory=dict)


# ─────────────────────────────────────────────
#  Scanner
# ─────────────────────────────────────────────
class NetworkScanner:
    """Asynchronous network scanner that detects responsive hosts.

    The scanner can attempt SSH-based OS discovery for hosts with port 22 open.
    """

    def __init__(
        self,
        ports: list[int],
        timeout: float,
        concurrency: int,
        credentials: list[dict],
    ) -> None:
        self.ports = ports
        self.timeout = timeout
        self.concurrency = concurrency
        self.credentials = credentials

    async def _iter_hosts(self, network: IPv4Network) -> AsyncIterator[str]:
        """Yield each host IP in the network one at a time."""
        for ip in network.hosts():
            yield str(ip)

    async def _check_port(self, ip: str, port: int) -> bool:
        """Return True if the TCP port is open on the given host."""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=self.timeout,
            )
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return True
        except (TimeoutError, ConnectionRefusedError, OSError):
            return False

    def _probe_host_via_netmiko(self, ip: str):
        """Probe OS via Netmiko (SSH)."""
        device_type = None
        for credential in self.credentials:
            label = credential.get('label')
            username = credential.get('username')
            password = credential.get('password')

            if username and password:
                # OS probing via Netmiko (SSH)
                logging.info(f'Probing OS on {ip} via Netmiko with credential {label}')
                device = {
                    'device_type': 'autodetect',
                    'host': ip,
                    'username': username,
                    'password': password,
                }
                logging.error(device)
                try:
                    guesser = SSHDetect(**device)
                except NetmikoAuthenticationException:
                    # Login failed
                    continue
                device_type = guesser.autodetect()

                if device_type:
                    return device_type, credential

        return None, None

    async def _scan_host(
        self,
        ip: str,
        semaphore: asyncio.Semaphore,
    ) -> HostResult | None:
        """
        Scan all configured ports on a single host.
        Returns a HostResult if at least one port is open, otherwise None.
        """
        async with semaphore:
            tasks = {port: asyncio.create_task(self._check_port(ip, port)) for port in self.ports}
            open_ports = []
            for open_port, task in tasks.items():
                if await task:
                    open_ports.append(open_port)
            open_ports.sort()

        if not open_ports:
            return None

        logger.info(f'Host {ip} is up (open_ports: {open_ports})')

        netmiko_device_type = None
        netdoc_plugin = None
        port = None

        if 22 in open_ports:
            # OS probing via Netmiko (SSH)
            port = 22
            netmiko_device_type, credential = self._probe_host_via_netmiko(ip)
            if netmiko_device_type == 'allied_telesis_awplus':
                netdoc_plugin = 'netmiko:allied_telesis:awplus:ssh'
            elif netmiko_device_type == 'aruba_oscx':
                netdoc_plugin = 'netmiko:aruba:aoscx:ssh'
            elif netmiko_device_type in ['cisco_ios', 'cisco_xe']:
                # Override device type
                netmiko_device_type = 'cisco_ios'
                netdoc_plugin = 'netmiko:cisco:ios:ssh'
            elif netmiko_device_type == 'cisco_nxos':
                netdoc_plugin = 'netmiko:cisco:nxos:ssh'
            elif netmiko_device_type == 'cisco_xr':
                netdoc_plugin = 'netmiko:cisco_xr:ssh'
            elif netmiko_device_type == 'hp_comware':
                netdoc_plugin = 'netmiko:hp:comware:ssh'
            elif netmiko_device_type == 'hp_procurve':
                netdoc_plugin = 'netmiko:hp:procurve:ssh'
            elif netmiko_device_type == 'huawei_vrp':
                netdoc_plugin = 'netmiko:huawei:vrp:ssh'
            elif netmiko_device_type == 'linux':
                netdoc_plugin = 'netmiko:linux::ssh'

        if not netdoc_plugin:
            logger.info(f'OS has not been detected on host {ip}')
            return None

        return HostResult(
            credential=credential,
            ip=ip,
            netdoc_plugin=netdoc_plugin,
            netmiko_device_type=netmiko_device_type,
            port=port,
        )

    async def _scan_network(self, network: IPv4Network) -> AsyncIterator[HostResult]:
        """
        Async generator: yield HostResult objects as hosts are scanned,
        without waiting for the entire subnet to complete.
        Keeps at most `concurrency` tasks in flight at any time.
        """
        semaphore = asyncio.Semaphore(self.concurrency)
        pending: set[asyncio.Task] = set()

        num_addresses = '1 host' if network.prefixlen == 32 else f'{network.num_addresses} hosts'
        logger.info(f'Scanning {network} - {num_addresses}')

        async for ip in self._iter_hosts(network):
            pending.add(asyncio.create_task(self._scan_host(ip, semaphore)))

            # Drain completed tasks whenever we hit the concurrency cap
            while len(pending) >= self.concurrency:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    if (result := t.result()) is not None:
                        yield result

        # Drain remaining tasks
        if pending:
            done, _ = await asyncio.wait(pending)
            for t in done:
                if (result := t.result()) is not None:
                    yield result

    async def scan(self, networks: list[IPv4Network]) -> AsyncIterator[HostResult]:
        """Yield HostResult objects for each active host in the target networks.

        Args:
            networks (list[IPv4Network]): list of networks to scan.

        Yields:
            HostResult: discovery result for each host with an open port.

        Usage:
            async for host in scanner.scan(["192.168.1.0/24"]):
                print(host.ip, host.open_ports)

        To collect a sorted list:
            results = sorted([h async for h in scanner.scan(networks)],
                             key=lambda r: ipaddress.ip_address(r.ip))
        """
        for network in networks:
            async for host in self._scan_network(network):
                yield host

    @staticmethod
    def save_inventory(hosts: list[HostResult], path: str) -> None:
        """Save a host inventory file in standard Ansible JSON format.

        Args:
            hosts (list[HostResult]): discovered hosts to serialize.
            path (str): path to the output JSON file.
        """
        inventory: dict[str, Any] = {
            '_meta': {'hostvars': {}},
            'all': {'hosts': []},
        }
        for host in hosts:
            inventory['_meta']['hostvars'][host.ip] = {
                'ansible_host': host.ip,
                'netmiko_device_type': host.netmiko_device_type,
                'ansible_password': host.credential['password'],
                'ansible_user': host.credential['username'],
                'ansible_port': host.port,
                'netdoc_plugin': host.netdoc_plugin,
            }
            inventory['all']['hosts'].append(host.ip)
        Path(path).write_text(json.dumps(inventory, indent=4, sort_keys=True))
        logger.info('Inventory saved to %s', path)
