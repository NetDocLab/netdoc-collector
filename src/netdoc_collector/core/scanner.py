"""Threaded network scanner and host discovery helpers.

This module implements a lightweight TCP scanner that can optionally probe
SSH endpoints with Netmiko to identify device types and map them to the
appropriate NetDoc plugin.
"""

import json
import logging
import socket
from netdoc_sdk.client import NetDocSyncClient
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from ipaddress import IPv4Network
from pathlib import Path
from typing import Any

from netmiko.exceptions import NetmikoAuthenticationException
from netmiko.ssh_autodetect import SSHDetect

logger = logging.getLogger('scanner')


# ---------------------------------------------------------------------------
#  Data model
# ---------------------------------------------------------------------------
@dataclass
class HostResult:
    """Result of a single host scan.

    Attributes:
        ip: host IP address.
        port: first responsive port discovered.
        netmiko_device_type: detected Netmiko device type.
        netdoc_plugin: mapped NetDoc plugin identifier.
        credential: credential record used for the scan attempt.
    """

    ip: str
    port: int | None = None
    netmiko_device_type: str | None = None
    netdoc_plugin: str | None = None
    credential: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Plugin mapping
# ---------------------------------------------------------------------------

_NETMIKO_TO_NETDOC: dict[str, tuple[str, str]] = {
    'allied_telesis_awplus': ('allied_telesis_awplus', 'netmiko:allied_telesis:awplus:ssh'),
    'aruba_oscx': ('aruba_oscx', 'netmiko:aruba:aoscx:ssh'),
    'cisco_ios': ('cisco_ios', 'netmiko:cisco:ios:ssh'),
    'cisco_xe': ('cisco_ios', 'netmiko:cisco:ios:ssh'),
    'cisco_nxos': ('cisco_nxos', 'netmiko:cisco:nxos:ssh'),
    'cisco_xr': ('cisco_xr', 'netmiko:cisco_xr:ssh'),
    'hp_comware': ('hp_comware', 'netmiko:hp:comware:ssh'),
    'hp_procurve': ('hp_procurve', 'netmiko:hp:procurve:ssh'),
    'huawei_vrp': ('huawei_vrp', 'netmiko:huawei:vrp:ssh'),
    'linux': ('linux', 'netmiko:linux::ssh'),
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class NetworkScanner:
    """Threaded network scanner that detects responsive hosts.

    Port scanning runs in a thread pool. SSH-based OS discovery is performed
    synchronously within each scanning thread for hosts with port 22 open.
    """

    def __init__(
        self,
        concurrency: int,
        credentials: list[dict],
        networks: list[IPv4Network],
        ports: list[int],
        timeout: float,
        client: NetDocSyncClient|None = None,
        excluded_addresses: list[str] = list,
    ) -> None:
        self.concurrency = concurrency
        self.credentials = credentials
        self.networks = networks
        self.ports = ports
        self.timeout = timeout
        self.client = client
        self.excluded_addresses = excluded_addresses

    def _check_port(self, ip: str, port: int) -> bool:
        """Return True when the TCP port is open on the given host."""
        try:
            with socket.create_connection((ip, port), timeout=self.timeout):
                return True
        except (TimeoutError, ConnectionRefusedError, OSError):
            return False

    def _probe_host_via_netmiko(self, ip: str) -> tuple[str | None, dict[str, str] | None]:
        """Probe the operating system of a host through Netmiko autodetection.

        The scanner tries each configured credential until one succeeds or all
        attempts fail.

        Args:
            ip: target host IP address.

        Returns:
            A (device_type, credential) tuple on success, or (None, None) if
            no credential matched or no device type could be determined.
        """
        for credential in self.credentials:
            label = credential.get('label')
            username = credential.get('username')
            password = credential.get('password')

            if not username or not password:
                # Skip credential sets that are incomplete.
                continue

            logger.info(
                'Probing OS on %s via Netmiko with credential %s',
                ip,
                label or '(unlabeled)',
            )
            try:
                guesser = SSHDetect(
                    device_type='autodetect',
                    host=ip,
                    username=username,
                    password=password,
                )
            except NetmikoAuthenticationException:
                # The credential was rejected; try the next one.
                logger.info('Credential %s rejected for %s', label or '(unlabeled)', ip)
                continue

            device_type = guesser.autodetect()
            if device_type:
                return device_type, credential

        logger.error('No more credentials available for %s — all attempts failed', ip)
        return None, None

    def _scan_host(self, ip: str) -> HostResult | None:
        """Scan a single host and return a discovery result if supported.

        Returns a HostResult only when a supported device is identified AND
        a working credential was found (i.e. login succeeded); otherwise
        returns None. This is what guarantees that every HostResult produced
        by scan() is safe to hand straight to discovery.

        Args:
            ip: target host IP address.
        """
        open_ports = sorted(port for port in self.ports if self._check_port(ip, port))

        if not open_ports:
            return None

        logger.info('Host %s is up (open_ports: %s)', ip, open_ports)

        if 22 not in open_ports:
            logger.info('Host %s has no SSH port open — skipping OS detection', ip)
            return None

        netmiko_device_type, matched_credential = self._probe_host_via_netmiko(ip)
        if not netmiko_device_type:
            return None

        mapping = _NETMIKO_TO_NETDOC.get(netmiko_device_type)
        if not mapping:
            logger.info(
                'Host %s has unsupported device type %s — skipping', ip, netmiko_device_type
            )
            return None

        normalized_type, netdoc_plugin = mapping
        logger.info('Host %s identified as %s', ip, netdoc_plugin)

        return HostResult(
            ip=ip,
            port=22,
            netmiko_device_type=normalized_type,
            netdoc_plugin=netdoc_plugin,
            credential=matched_credential or {},
        )

    def scan(self) -> list[HostResult]:
        """Scan all configured networks and return discovered hosts.

        The scan runs concurrently and returns results sorted by IP address.
        This call blocks until the scan phase is fully complete; the caller
        is expected to run the discovery phase only after this method
        returns, so the two phases stay strictly sequential (scan finishes
        entirely, then discovery starts on its result).

        Returns:
            List of HostResult for each discovered and identified host.
        """
        all_ips = [str(ip) for network in self.networks for ip in network.hosts()]

        total = len(all_ips)
        logger.info('Scanning %d hosts across %d network(s)', total, len(self.networks))

        results: list[HostResult] = []

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {executor.submit(self._scan_host, ip): ip for ip in all_ips}
            for future in as_completed(futures):
                ip = futures[future]
                try:
                    result = future.result()
                except Exception:
                    logger.exception('Unexpected error scanning host %s', ip)
                    continue
                if result is not None:
                    results.append(result)

        results.sort(key=lambda r: tuple(int(p) for p in r.ip.split('.')))
        logger.info('Scan complete: %d/%d hosts identified', len(results), total)
        return results

    @staticmethod
    def build_inventory(hosts: list[HostResult]) -> dict[str, Any]:
        """Build an in-memory Ansible-style inventory dict from scan results.

        Only hosts that were successfully identified during the scan are
        included here: scan() already drops any host whose credentials
        failed or whose OS/plugin could not be resolved, so every entry
        returned by this method has a working login and a supported NetDoc
        plugin, ready to be handed directly to the discovery task.

        Args:
            hosts: discovered hosts to serialize.

        Returns:
            Inventory dict in the same shape as the on-disk JSON format
            produced by save_inventory().
        """
        inventory: dict[str, Any] = {
            '_meta': {'hostvars': {}},
            'all': {'hosts': []},
        }
        for host in hosts:
            inventory['_meta']['hostvars'][host.ip] = {
                'ansible_host': host.ip,
                'ansible_password': host.credential.get('password'),
                'ansible_port': host.port,
                'ansible_user': host.credential.get('username'),
                'netdoc_plugin': host.netdoc_plugin,
                'netmiko_device_type': host.netmiko_device_type,
            }
            inventory['all']['hosts'].append(host.ip)
        return inventory

    @classmethod
    def complete(cls, hosts, inventory_file=None) -> None:
        # TODO
        """Save a host inventory file in standard Ansible JSON format.

        Kept for debugging/audit purposes only: discovery no longer needs to
        read this file back, since scanned hosts are now fed directly into
        the discovery run via build_inventory().

        Args:
            hosts: discovered hosts to serialize.
            path: path to the output JSON file.
        """
        inventory = cls.build_inventory(hosts)
        if inventory_file:
            logger.info('Writing scan results to %s', inventory_file)
            Path(inventory_file).write_text(json.dumps(inventory, indent=4, sort_keys=True))
            logger.info('Inventory saved to %s', inventory_file)
