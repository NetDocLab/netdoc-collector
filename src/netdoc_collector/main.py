#!/usr/bin/env python3
"""NetDoc collector command-line entrypoint and task orchestration.

This module defines the synchronous collector application that can run
in either stand-alone or managed mode. It parses CLI arguments, loads
configuration, initializes Nornir, executes discovery tasks, and handles
upload of raw discovery payloads to the NetDoc backend.
"""

import argparse
import getpass
import ipaddress
import json
import logging
import os
import signal
import socket
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from threading import Event, Thread

import psutil
from netdoc_sdk.client import NetDocSyncClient
from netdoc_sdk.exceptions import AuthenticationError, ValidationError
from nornir import InitNornir
from nornir.core.plugins.inventory import InventoryPluginRegister

from netdoc_collector.core.ansible_inventory import NetDocAnsibleInventory
from netdoc_collector.core.scanner import NetworkScanner
from netdoc_collector.core.tasks import (
    discovery_task,
    mark_job_as_completed,
    send_collector_heartbeat,
)
from netdoc_collector.core.utils import (
    REPORT_PATH_FMT,
    MainLogCollector,
    cleanup_old_snapshots,
    load_config,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s  %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
    handlers=[
        logging.FileHandler('netdoc_collector.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def _stop_background_threads(threads: list[Thread], stop_event: Event) -> None:
    """Signal all background threads to stop and wait for them to finish.

    Args:
        threads: list of running background threads.
        stop_event: shared stop event to signal threads.
    """
    stop_event.set()
    for thread in threads:
        thread.join(timeout=5)
    threads.clear()


def main() -> int:
    """Parse CLI arguments and execute the NetDoc collector workflow.

    Returns:
        int: exit code; 0 on success, non-zero on failure.
    """

    parser = argparse.ArgumentParser(description='NetDoc collector')

    # Scanner
    parser.add_argument('-s', '--scan', action='store_true', help='Scan networks for devices')
    parser.add_argument(
        '-n', '--network', action='append', help='Network CIDR (can be specified multiple times)'
    )

    # Stand-alone + managed mode
    parser.add_argument('-c', '--config', default='config.yaml', help='Path to config.yaml')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('-o', '--output', help='Override output directory')
    parser.add_argument('-r', '--retention', help='Override retention', type=int)
    parser.add_argument('-t', '--cmd-timeout', help='Override CMD timeout', type=int)
    parser.add_argument('-w', '--workers', help='Override worker instances', type=int)

    # Stand-alone mode
    parser.add_argument('-i', '--inventory', help='Override local inventory file')
    parser.add_argument('-p', '--password', default='secrets.yaml', help='Path to secrets.yaml')

    # Managed mode
    parser.add_argument('-T', '--timeout', help='Override backend timeout', type=int)
    parser.add_argument('-u', '--url', help='Override backend URL')
    parser.add_argument('--token', default=None, help='Override API token')
    parser.add_argument('--insecure', action='store_true', help='Override backend insecure cert')

    args = parser.parse_args()

    # Reading arguments: stand-alone + managed mode
    cfg = load_config(args.config)
    if args.debug:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s  %(levelname)-8s  %(name)s  %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S',
        )
        console_handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.DEBUG)

    scan = args.scan
    input_networks = args.network or []
    cmd_timeout = args.cmd_timeout or cfg.get('cmd_timeout') or 120
    num_workers = args.workers or cfg.get('workers') or 5
    output_dir = args.output or cfg.get('output', './output')
    retention = args.retention or cfg.get('retention') or 5
    report_path = Path(output_dir) / Path(datetime.now().strftime(REPORT_PATH_FMT))

    # Reading arguments: stand-alone mode
    inventory_file = args.inventory or cfg.get('inventory', 'inventory.json')

    # Reading arguments: managed mode
    backend_data = cfg.get('backend', {})
    backend_timeout = args.timeout or backend_data.get('timeout') or 120
    backend_token = os.getenv('NETDOC_TOKEN') or args.token or backend_data.get('token')
    backend_url = args.url or backend_data.get('url', 'http://localhost:8000')
    backend_insecure = args.insecure or backend_data.get('insecure', True)

    # Managed mode configuration
    background_threads: list[Thread] = []
    cancel_event = Event()
    claim_token: str | None = None
    client: NetDocSyncClient | None = None
    collector_name = f'{getpass.getuser()}@{socket.getfqdn()}'
    collector_version = version('netdoc-collector')
    idempotency_key: str | None = None
    job_id: str | None = None
    job_log_collector: MainLogCollector | None = None
    # Shared stop event: any background task can set this to request a clean shutdown.
    stop_event = Event()

    # Evaluating mode
    if backend_url and backend_token:
        job_log_collector = MainLogCollector()
        logging.getLogger().addHandler(job_log_collector)

        logger.info(
            'Running in managed mode (backend_url=%s, collector_name=%s)',
            backend_url,
            collector_name,
        )
        client = NetDocSyncClient(
            base_url=backend_url,
            token=backend_token,
            timeout=backend_timeout,
            verify=not backend_insecure,
        )

        # Single heartbeat to validate token
        try:
            client.collectors_heartbeat(name=collector_name, version=collector_version)
        except (AuthenticationError, ValidationError) as exc:
            logger.error(exc.message)
            logging.getLogger().removeHandler(job_log_collector)
            return 11

        # Periodically send a collector heartbeat; stop_event is set on failure.
        heartbeat_thread = Thread(
            target=send_collector_heartbeat,
            kwargs={
                'collector_client': client,
                'name': collector_name,
                'version': collector_version,
                'stop_event': stop_event,
            },
            daemon=True,
            name='heartbeat',
        )
        heartbeat_thread.start()
        background_threads.append(heartbeat_thread)

    elif scan:
        # Running in stand-alone mode (scan)
        logger.info('Running in stand-alone mode (scan)')

        # Load credentials from secrets.yaml
        secrets = load_config(args.password)
        credentials = secrets.get('credentials', {})
        if not credentials:
            logger.error('No credentials found in %s', args.password)
            return 6

        # Validate networks to scan
        networks = []
        if not input_networks:
            # Add local networks
            for _iface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family != socket.AF_INET:
                        continue
                    network = ipaddress.IPv4Network(f'{addr.address}/{addr.netmask}', strict=False)
                    if network.is_loopback or not network.is_private:
                        # Exclude loopback and public networks
                        continue
                    networks.append(network)
        else:
            for input_network in input_networks:
                try:
                    network = ipaddress.IPv4Network(input_network, strict=False)
                except (ipaddress.NetmaskValueError, ValueError):
                    logger.error('Network %s is invalid', input_network)
                    return 5
                networks.append(network)

    elif inventory_file:
        # Running in stand-alone mode (discovery)
        logger.info('Running in stand-alone mode (inventory_file=%s)', inventory_file)
        with open(inventory_file) as fh:
            try:
                inventory = json.load(fh)
            except json.JSONDecodeError:
                logger.error('Invalid JSON in inventory file: %s', inventory_file)
                return 3
    else:
        logger.error('At least inventory_file or backend_url and backend_token are required')
        return 4

    if client:
        # Managed mode
        # Register signal handlers for graceful shutdown
        def _handle_signal(signum, frame) -> None:
            logger.warning('Signal %d received', signum)
            if job_id and claim_token:
                job_logs = job_log_collector.drain() if job_log_collector else []
                final_status = 'canceled' if cancel_event.is_set() else 'failed'
                try:
                    mark_job_as_completed(
                        client,
                        id=job_id,
                        claim_token=claim_token,
                        status=final_status,
                        logs=job_logs,
                    )
                except ValidationError as exc:
                    logger.error(
                        'Failed to close job %s as %s: %s', job_id, final_status, exc.message
                    )
                except Exception:
                    logging.exception('Unexpected error closing job %s on signal', job_id)
            _stop_background_threads(background_threads, stop_event)
            sys.exit(1)

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        # Claim job
        try:
            job = client.discovery_jobs_claim()
            if not job:
                logger.info('No job to claim')
                _stop_background_threads(background_threads, stop_event)
                return 0
        except (AuthenticationError, ValidationError) as exc:
            logger.error(exc.message)
            _stop_background_threads(background_threads, stop_event)
            return 7

        job_id = job.id
        idempotency_key = job.idempotency_key
        claim_token = job.claim_token
        inventory = job.inventory

    elif scan:
        # Stand-alone mode (scan)
        scan_workers = num_workers * 10
        scanner = NetworkScanner(
            ports=[22, 23, 80, 443],
            timeout=0.5,
            concurrency=scan_workers,
            credentials=credentials,
            networks=networks,
        )
        logger.info('Starting scan with %d workers', scan_workers)
        hosts = list(scanner.scan())
        scanner.save_inventory(hosts, inventory_file)
        return 0
    else:
        # Stand-alone mode (discovery)
        logger.info('Reading inventory_file=%s', inventory_file)
        with open(inventory_file) as fh:
            try:
                inventory = json.load(fh)
            except json.JSONDecodeError:
                logger.error('Invalid JSON in inventory file: %s', inventory_file)
                return 8

    # Abort early if a heartbeat already failed during setup.
    if stop_event.is_set():
        logger.error('A background thread failed during setup; aborting.')
        _stop_background_threads(background_threads, stop_event)
        return 9

    # Initialising Nornir for managed and stand-alone modes
    logger.info('Initialising Nornir (num_workers=%d)', num_workers)
    InventoryPluginRegister.register('NetDocAnsibleInventory', NetDocAnsibleInventory)
    nr = InitNornir(
        runner={'plugin': 'threaded', 'options': {'num_workers': num_workers}},
        inventory={
            'plugin': 'NetDocAnsibleInventory',
            'options': {'inventory': inventory},
        },
        logging={'enabled': False},
    )

    # Running discovery tasks
    logger.info('Running collector on %d device(s)', len(nr.inventory.hosts))
    results = nr.run(
        task=discovery_task,
        report_path=report_path,
        cmd_timeout=cmd_timeout,
        client=client,
        job_id=job_id,
        idempotency_key=idempotency_key,
        claim_token=claim_token,
        cancel_event=cancel_event,
    )
    total_hosts = len(results.values())
    failed_hosts = sum(1 for r in results.values() if r.failed)
    completed_hosts = total_hosts - failed_hosts
    logger.info('Discovery completed on %i/%i hosts', completed_hosts, total_hosts)

    # Cleaning older outputs
    cleanup_old_snapshots(output_dir, retention)

    # Closing task (managed mode)
    if client and job_id and claim_token:
        # Close the job
        if cancel_event.is_set():
            final_status = 'canceled'
        elif completed_hosts == 0:
            final_status = 'failed'
        else:
            final_status = 'completed'

        job_logs = job_log_collector.drain() if job_log_collector else []
        try:
            mark_job_as_completed(
                client, id=job_id, claim_token=claim_token, status=final_status, logs=job_logs
            )
            logger.info('Job %s is %s', job_id, final_status)
        except ValidationError as exc:
            logger.error('Failed to complete job: %s', exc)
            if job_log_collector:
                logging.getLogger().removeHandler(job_log_collector)
            _stop_background_threads(background_threads, stop_event)
            return 10

    if job_log_collector:
        logging.getLogger().removeHandler(job_log_collector)

    # Cancel all background tasks before exiting cleanly.
    _stop_background_threads(background_threads, stop_event)
    return 2 if failed_hosts else 0


def entrypoint() -> int:
    """Execute the collector entrypoint from a console script."""
    return main()


if __name__ == '__main__':
    sys.exit(main())
