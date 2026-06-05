"""
network_scan.py - Async TCP network scanner for Linux (no root required).

Usage:
  python network_scan.py 192.168.1.0/24
  python network_scan.py 192.168.1.0/24 10.0.0.0/24 --ports 22 80 443
  python network_scan.py 192.168.1.0/24 --concurrency 100 --timeout 1.5
  python network_scan.py 192.168.1.0/24 --output results.json
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from ipaddress import IPv4Network

from netmiko.exceptions import NetmikoAuthenticationException
from netmiko.ssh_autodetect import SSHDetect

logger = logging.getLogger('scanner')


# ─────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────
@dataclass
class HostResult:
    ip: str
    port: int | None = None
    device_type: str | None = None
    credential: dict[str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {'ip': self.ip, 'port': self.port, 'device_type': self.device_type}


# ─────────────────────────────────────────────
#  Scanner
# ─────────────────────────────────────────────
class NetworkScanner:
    def __init__(
        self,
        ports: list[int],
        timeout: float,
        concurrency: int,
        credentials: dict[str],
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
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except (TimeoutError, ConnectionRefusedError, OSError):
            return False

    def _probe_host_via_netmiko(self, ip: str):
        """Probe OS via Netmiko (SSH)."""
        device_type = None
        for credential in self.credentials:
            username = credential.get('username')
            password = credential.get('password')

            if username and password:
                # OS probing via Netmiko (SSH)
                logging.info(f'Probing OS on {ip} via Netniko with username {username}')
                device = {
                    'device_type': 'autodetect',
                    'host': ip,
                    'username': username,
                    'password': password,
                }
                try:
                    guesser = SSHDetect(**device)
                except NetmikoAuthenticationException:
                    # Login failed
                    continue
                device_type = guesser.autodetect()

                if device_type:
                    return device_type

        return None

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
            for port, task in tasks.items():
                if await task:
                    open_ports.append(port)
            open_ports.sort()

        if not open_ports:
            return None

        logger.info(f'Host {ip} is up (open_ports: {open_ports})')

        device_type = None
        port = None
        if 22 in open_ports:
            # OS probing via Netmiko (SSH)
            device_type = self._probe_host_via_netmiko(ip)
            port = 22

        if not device_type:
            logger.info(f'OS has not been detected on host {ip}')
            return None

        return HostResult(ip=ip, port=port, device_type=device_type)

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
        """
        Async generator: yield HostResult for each active host across all networks.

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
