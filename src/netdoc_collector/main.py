#!/usr/bin/env python3
"""Command-line entry point and orchestration logic for NetDoc Collector.

This module parses CLI arguments, loads configuration, initializes Nornir,
executes discovery tasks, and optionally pushes the resulting data to the
NetDoc backend in managed mode. Collector can run either in stand-alone or
managed mode.

Stand-alone mode: Scan and discovery are two distinct, phases when running
in stand-alone mode. The --network parameter force collector to scan networks
and update (merge) the inventory file. Without the --network paramter the collector
discovers the hosts included in the inventory file.

Managed mode: the static-inventory discovery (nr.run() on job.inventory) and
the network scan phase (which, per host identified, triggers its own
immediate discovery — see NetworkScanner._scan_host) run concurrently: the
scan is kicked off on a background thread right away, and the static
discovery run starts immediately afterwards on the main thread without
waiting for the scan to finish. The job is only closed once BOTH phases
have completed: main() always waits for the scan thread (via
scan_future.result()) after the static-inventory nr.run() call returns,
before computing final counters and closing the job.
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from threading import Event, Thread

from netdoc_sdk.client import NetDocSyncClient
from netdoc_sdk.exceptions import AuthenticationError, ValidationError
from nornir import InitNornir
from nornir.core.plugins.inventory import InventoryPluginRegister

from netdoc_collector.core.ansible_inventory import (
    NetDocAnsibleInventory,
    NetDocAnsibleInventoryError,
)
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
        threads: running background threads that should be stopped.
        stop_event: shared event used to request shutdown.
    """
    stop_event.set()
    for thread in threads:
        thread.join(timeout=5)
    threads.clear()


def main() -> int:
    """Parse CLI arguments and run the collector workflow.

    Returns:
        int: exit code. Zero indicates success; non-zero values indicate
            failures or abnormal termination.
    """

    parser = argparse.ArgumentParser(description='NetDoc collector')

    # Scanner

    # Stand-alone + managed mode
    parser.add_argument('-c', '--config', default='config.yaml', help='Path to config.yaml')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('-o', '--output', help='Override output directory')
    parser.add_argument('-r', '--retention', help='Override retention', type=int)
    parser.add_argument('-t', '--cmd-timeout', help='Override CMD timeout', type=int)
    parser.add_argument('-w', '--workers', help='Override worker instances', type=int)

    # Stand-alone mode
    parser.add_argument(
        '-n',
        '--network',
        action='append',
        help='Networks to scan (CIDR, can be specified multiple times)',
    )
    parser.add_argument('-i', '--inventory', help='Override local inventory file')
    parser.add_argument('-s', '--secrets', default='secrets.yaml', help='Path to secrets.yaml')

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

    cmd_timeout = args.cmd_timeout or cfg.get('cmd_timeout') or 240
    num_workers = args.workers or cfg.get('workers') or 5
    output_dir = args.output or cfg.get('output', './output')
    retention = args.retention or cfg.get('retention') or 5
    report_path = Path(output_dir) / Path(datetime.now().strftime(REPORT_PATH_FMT))

    # Reading arguments: stand-alone mode
    inventory_file = args.inventory or cfg.get('inventory', 'inventory.json')
    input_networks = args.network or []

    # Reading arguments: managed mode
    backend_data = cfg.get('backend', {})
    backend_timeout = args.timeout or backend_data.get('timeout') or 120
    backend_token = os.getenv('NETDOC_TOKEN') or args.token or backend_data.get('token')
    backend_url = args.url or backend_data.get('url', 'http://localhost:8000')
    backend_insecure = args.insecure or backend_data.get('insecure', False)

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

    # Register the Ansible-style inventory plugin exactly once, before any
    # Nornir instance is created anywhere (the main static-inventory run
    # below, and the per-host runs NetworkScanner._scan_host triggers on its
    # own background thread in managed mode). Centralizing this avoids two
    # threads racing to register the same plugin name concurrently.
    InventoryPluginRegister.register('NetDocAnsibleInventory', NetDocAnsibleInventory)

    # Managed-mode scan phase (background thread) and the resulting
    # scan-triggered discovery stats. Stay at their defaults in every mode
    # that does not run a concurrent scan (stand-alone discovery-only mode).
    scan_executor: ThreadPoolExecutor | None = None
    scan_future = None
    scanner: NetworkScanner | None = None
    scan_completed_hosts = 0
    scan_failed_hosts = 0
    scan_crashed = False

    # Evaluate whether runtime should use managed or stand-alone mode.
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

    elif input_networks:
        # Running in stand-alone mode (scan).
        #
        # There is no static inventory to discover in parallel here (that is
        # only a managed-mode concept, see below), so this path stays fully
        # sequential: scan, then persist results, then exit.
        logger.info('Running in stand-alone mode (scan)')

        # Load credentials from secrets.yaml
        secrets = load_config(args.secrets)
        credentials = secrets.get('credentials', {})
        if not credentials:
            logger.error('No credentials found in %s', args.secrets)
            return 6

        # Validate networks to scan
        networks = []
        for input_network in input_networks:
            try:
                network = ipaddress.IPv4Network(input_network, strict=False)
            except (ipaddress.NetmaskValueError, ValueError):
                logger.error('Network %s is invalid', input_network)
                return 5
            networks.append(network)

        # Scan (stand-alone)
        scan_workers = num_workers * 10
        scanner = NetworkScanner(
            cancel_event=cancel_event,
            cmd_timeout=cmd_timeout,
            concurrency=scan_workers,
            credentials=credentials,
            networks=networks,
            ports=[22, 23, 80, 443],
            report_path=report_path,
            timeout=0.5,
        )
        logger.info('Starting scan with %d workers', scan_workers)
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
        logger.info(
            'Scan-triggered discovery completed on %d/%d host(s)',
            scan_completed_hosts,
            scan_completed_hosts + scan_failed_hosts,
        )
        scanner.complete(hosts, inventory_file=inventory_file)
        return 0

    elif inventory_file:
        # Running in stand-alone mode.
        logger.info('Running in stand-alone mode (discovery)')
        try:
            logger.info('Loading inventory file: %s)', inventory_file)
            with open(inventory_file) as fh:
                inventory = json.load(fh)
        except FileNotFoundError:
            logger.warning('Inventory file not found: %s', inventory_file)
            inventory = {'_meta': {'hostvars': {}}, 'all': {'hosts': []}}
        except json.JSONDecodeError:
            logger.error('Invalid JSON file: %s', inventory_file)
            return 3

    else:
        logger.error('At least inventory_file or backend_url + backend_token are required')
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
            if scan_executor is not None:
                scan_executor.shutdown(wait=False, cancel_futures=True)
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

        # Network scan parameters
        credentials = job.credentials
        input_networks = job.network_ranges
        excluded_addresses = job.known_ip_addresses

        # Validate networks to scan
        networks = []
        for input_network in input_networks:
            try:
                network = ipaddress.IPv4Network(input_network, strict=False)
            except (ipaddress.NetmaskValueError, ValueError):
                logger.error('Network %s is invalid', input_network)
                return 5
            networks.append(network)

        # Scan (managed): kicked off on a background thread and NOT awaited
        # here. The static-inventory discovery below (nr.run()) starts right
        # after this, on the main thread, so the two phases run concurrently.
        # We only ever wait for this future right before computing the job's
        # final counters/status, further down.
        scan_workers = num_workers * 10
        scanner = NetworkScanner(
            cancel_event=cancel_event,
            cmd_timeout=cmd_timeout,
            concurrency=scan_workers,
            credentials=credentials,
            networks=networks,
            ports=[22, 23, 80, 443],
            report_path=report_path,
            timeout=0.5,
            claim_token=claim_token,
            client=client,
            excluded_addresses=excluded_addresses,
            idempotency_key=idempotency_key,
            job_id=job_id,
        )
        logger.info('Starting scan with %d workers in the background', scan_workers)
        scan_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='scan')
        scan_future = scan_executor.submit(scanner.scan)

    # Abort early if a heartbeat already failed during setup.
    if stop_event.is_set():
        logger.error('A background thread failed during setup; aborting.')
        if scan_executor is not None:
            scan_executor.shutdown(wait=False, cancel_futures=True)
        _stop_background_threads(background_threads, stop_event)
        return 9

    # Initialize Nornir for managed and stand-alone modes.
    logger.info('Initialising Nornir (num_workers=%d)', num_workers)
    try:
        nr = InitNornir(
            runner={'plugin': 'threaded', 'options': {'num_workers': num_workers}},
            inventory={
                'plugin': 'NetDocAnsibleInventory',
                'options': {'inventory': inventory},
            },
            logging={'enabled': False},
        )
    except NetDocAnsibleInventoryError:
        logger.error('Invalid inventory: %s', inventory)
        if scan_executor is not None:
            scan_executor.shutdown(wait=False, cancel_futures=True)
        return 12

    # Run discovery tasks on the static inventory (managed + stand-alone
    # mode). In managed mode, this runs concurrently with the scan phase
    # started above on its own thread — this call does not wait for it.
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
    static_inventory_total = len(results.values())
    static_inventory_failed = sum(1 for r in results.values() if r.failed)
    static_inventory_completed = static_inventory_total - static_inventory_failed
    logger.info(
        'Static-inventory discovery completed on %i/%i hosts',
        static_inventory_completed,
        static_inventory_total,
    )

    # Always wait for the scan phase to finish before proceeding to close
    # the job — this is the point where "before exiting, always wait for
    # the scanner" is enforced. By the time we get here the scan has
    # typically already made significant progress (it started before
    # nr.run() above), so this wait is usually short or immediate.
    if scan_future is not None and scanner is not None:
        try:
            hosts = scan_future.result()
        except Exception:
            logger.exception('Scan phase failed')
            hosts = []
            scan_crashed = True
        finally:
            if scan_executor:
                scan_executor.shutdown(wait=True)

        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
        logger.info(
            'Scan-triggered discovery completed on %d/%d host(s)',
            scan_completed_hosts,
            scan_completed_hosts + scan_failed_hosts,
        )
        scanner.complete(hosts)

    # Combine the scan-triggered discovery phase (managed mode only) with
    # the static-inventory discovery phase above before deciding on the
    # job's final status and exit code. Logging for each phase stays
    # separate (see above); only the totals used for closing the job are
    # merged here.
    total_hosts = static_inventory_total + scan_completed_hosts + scan_failed_hosts
    completed_hosts = static_inventory_completed + scan_completed_hosts
    failed_hosts = static_inventory_failed + scan_failed_hosts
    logger.info('Discovery completed on %i/%i hosts overall', completed_hosts, total_hosts)

    # Clean older outputs.
    cleanup_old_snapshots(output_dir, retention)

    # Close the job in managed mode.
    if client and job_id and claim_token:
        # Close the job.
        if cancel_event.is_set():
            final_status = 'canceled'
        elif scan_crashed or (total_hosts > 0 and completed_hosts == 0):
            # Either the scan phase itself crashed (not just individual
            # hosts failing discovery), or hosts were identified (from scan
            # and/or static inventory) but every single one of them failed.
            final_status = 'failed'
        else:
            # Either every host succeeded, some succeeded and some failed,
            # or there was simply nothing to discover at all (total_hosts
            # == 0) — both phases still ran to completion, so the job is
            # considered completed rather than failed in that case.
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

    # Cancel all background tasks before exiting cleanly. This line is only
    # ever reached after BOTH the static-inventory discovery (nr.run above)
    # and the scan-triggered discovery phase (scan_future.result() above)
    # have completed.
    _stop_background_threads(background_threads, stop_event)
    return 2 if failed_hosts or scan_crashed else 0


def entrypoint() -> int:
    """Execute the collector entry point from a console script."""
    return main()


if __name__ == '__main__':
    sys.exit(main())
