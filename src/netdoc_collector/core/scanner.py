"""Threaded network scanner and host discovery helpers.

This module implements a lightweight TCP scanner that can optionally probe
SSH endpoints with Netmiko to identify device types and map them to the
appropriate NetDoc plugin.
"""

import json
import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from ipaddress import IPv4Network
from pathlib import Path
from typing import Any

from netdoc_sdk.client import NetDocSyncClient
from netmiko.exceptions import NetmikoAuthenticationException
from netmiko.ssh_autodetect import SSHDetect
from nornir import InitNornir

from netdoc_collector.core.tasks import discovery_task

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
    discovery_failed: bool = False


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
        cancel_event,
        cmd_timeout: int,
        concurrency: int,
        credentials: list[dict],
        networks: list[IPv4Network],
        ports: list[int],
        report_path: Path,
        timeout: float,
        claim_token: str | None = None,
        client: NetDocSyncClient | None = None,
        excluded_addresses: list[str] | None = None,
        idempotency_key: str | None = None,
        job_id: str | None = None,
    ) -> None:
        self.cancel_event = cancel_event
        self.cmd_timeout = cmd_timeout
        self.concurrency = concurrency
        self.credentials = credentials
        self.networks = networks
        self.ports = ports
        self.report_path = report_path
        self.timeout = timeout

        self.claim_token = claim_token
        self.client = client
        self.excluded_addresses = excluded_addresses or []
        self.idempotency_key = idempotency_key
        self.job_id = job_id

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

        host_result = HostResult(
            ip=ip,
            port=22,
            netmiko_device_type=normalized_type,
            netdoc_plugin=netdoc_plugin,
            credential=matched_credential or {},
        )

        if self.client:
            # Run single discovery (num_worker=1)
            inventory = self.build_inventory([host_result])
            nr = InitNornir(
                runner={'plugin': 'threaded', 'options': {'num_workers': 1}},
                inventory={
                    'plugin': 'NetDocAnsibleInventory',
                    'options': {'inventory': inventory},
                },
                logging={'enabled': False},
            )
            logger.info('Running collector on %s', ip)
            results = nr.run(
                task=discovery_task,
                report_path=self.report_path,
                cmd_timeout=self.cmd_timeout,
                client=self.client,
                job_id=self.job_id,
                idempotency_key=self.idempotency_key,
                claim_token=self.claim_token,
                cancel_event=self.cancel_event,
            )
            failed = sum(1 for r in results.values() if r.failed)
            host_result.discovery_failed = bool(failed)
            if failed:
                logger.info('Discovery failed on %s', ip)
            else:
                logger.info('Discovery completed on %s', ip)

        return host_result

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
        all_ips = [
            str(ip)
            for network in self.networks
            for ip in network.hosts()
            if str(ip) not in self.excluded_addresses
        ]
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
                'netdoc_credential_id': host.credential.get('id'),
                'netdoc_plugin': host.netdoc_plugin,
                'netmiko_device_type': host.netmiko_device_type,
            }
            inventory['all']['hosts'].append(host.ip)
        return inventory

    @classmethod
    def complete(cls, hosts, inventory_file=None) -> None:
        """Complete a scan in both stand-alone and managed mode.

        In stand-alonemode, inventory file is saved locally in standard Ansible JSON format.
        If an inventory file already exists, the two files are merged.

        In managed mode, data are uploaded to the backend.

        Args:
            hosts: discovered hosts to serialize.
            inventory_file: path to the output JSON file (stand-alone mode).
        """
        inventory = cls.build_inventory(hosts)
        if inventory_file:
            current_inventory = {}
            try:
                logger.info('Loading inventory file: %s)', inventory_file)
                with open(inventory_file) as fh:
                    current_inventory = json.load(fh)
            except FileNotFoundError:
                logger.info('Inventory file not found: %s', inventory_file)
            except json.JSONDecodeError:
                logger.warning('Invalid JSON file: %s', inventory_file)

            if current_inventory:
                logger.info('Merging scan results to %s', inventory_file)
                # Merging groups
                merged_inventory = current_inventory | inventory
                # Merging hosts
                merged_hosts = (
                    current_inventory.get('_meta', {}).get('hostvars', {})
                    | inventory['_meta']['hostvars']
                )
                merged_inventory['_meta']['hostvars'] = merged_hosts
                # Updating all group
                merged_inventory['all']['hosts'] = sorted(
                    merged_inventory['_meta']['hostvars'].keys()
                )
                Path(inventory_file).write_text(
                    json.dumps(merged_inventory, indent=4, sort_keys=True)
                )
                return

            logger.info('Writing scan results to %s', inventory_file)
            Path(inventory_file).write_text(json.dumps(inventory, indent=4, sort_keys=True))
            logger.info('Inventory saved to %s', inventory_file)
            return

    @staticmethod
    def summarize_discovery(hosts: list[HostResult]) -> tuple[int, int]:
        """Summarize the immediate managed-mode discovery outcome for scanned hosts.

        Only meaningful when the scanner ran with a client (managed mode),
        since that is the only case where _scan_host runs discovery
        immediately for each identified host. Hosts with discovery_failed is
        None (discovery not run, e.g. stand-alone scan) are excluded from
        both counts.

        Args:
            hosts: hosts returned by scan().

        Returns:
            A (completed_count, failed_count) tuple.
        """
        completed = sum(1 for h in hosts if h.discovery_failed is False)
        failed = sum(1 for h in hosts if h.discovery_failed is True)
        return completed, failed
