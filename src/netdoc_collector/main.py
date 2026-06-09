#!/usr/bin/env python3
"""NetDoc collector command-line entrypoint and task orchestration.

This module defines the asynchronous collector application that can run
in either stand-alone or managed mode. It parses CLI arguments, loads
configuration, initializes Nornir, executes discovery tasks, and handles
upload of raw discovery payloads to the NetDoc backend.
"""

import argparse
import asyncio
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

import psutil
from netdoc_sdk.client import NetDocClient
from netdoc_sdk.exceptions import NetDocError, ValidationError
from nornir import InitNornir
from nornir.core.plugins.inventory import InventoryPluginRegister

from netdoc_collector.core.ansible_inventory import NetDocAnsibleInventory
from netdoc_collector.core.scanner import NetworkScanner
from netdoc_collector.core.tasks import (
    discovery_task,
    mark_job_as_failed,
    send_collector_heartbeat,
    send_job_heartbeat,
)
from netdoc_collector.core.utils import (
    REPORT_PATH_FMT,
    LogListHandler,
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
log_list_handler = LogListHandler()
log_list_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(log_list_handler)
logger = logging.getLogger(__name__)


async def main() -> int:
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
    parser.add_argument('--verify', default=None, help='Override backend cert verification')

    args = parser.parse_args()

    # Reading arguments: stand-alone + managed mode
    cfg = load_config(args.config)
    if args.debug:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
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
    # backend_verify = args.verify or backend_data.get("verify", True)  # TODO

    # Managed mode configuration
    background_tasks = set()
    claim_token = None
    client = None
    collector_name = f'{getpass.getuser()}@{socket.getfqdn()}'
    collector_version = version('netdoc-collector')
    idempotency_key = None
    job_id = None

    # Evaluating mode
    if backend_url and backend_token:
        # Running in managed mode
        logging.info(
            'Running in managed mode (backend_url=%s, collector_name=%s)',
            backend_url,
            collector_name,
        )
        client = NetDocClient(base_url=backend_url, token=backend_token, timeout=backend_timeout)

        # Regurlary send collector heartbeat
        collector_heartbeat_task = asyncio.create_task(
            send_collector_heartbeat(client, name=collector_name, version=collector_version)
        )
        background_tasks.add(collector_heartbeat_task)
        collector_heartbeat_task.add_done_callback(background_tasks.discard)
    elif scan:
        # Running in stand-alone mode (scan)

        # Load credentials from secrets.yaml
        secrets = load_config(args.password)
        credentials = secrets.get('credentials', {})
        if not credentials:
            logging.error('No credential found')
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

                    if network.is_loopback:
                        # Exclude loopback
                        continue

                    if not network.is_private:
                        # Include private networks only
                        continue

                    networks.append(network)
        else:
            for input_network in input_networks:
                try:
                    network = ipaddress.IPv4Network(input_network, strict=False)
                except ipaddress.NetmaskValueError:
                    logging.error(f'Network {input_network} is invalid')
                    return 5
                networks.append(network)
    elif inventory_file:
        # Running in stand-alone mode (discovery)
        logging.info('Running in stand-alone mode (inventory_file=%s)', inventory_file)
        with open(inventory_file) as fh:
            try:
                inventory = json.load(fh)
            except json.JSONDecodeError:
                logger.error('Invalid JSON in inventory file: %s', inventory_file)
                return 3
    else:
        logger.error('At least inventory_file or backend_url and backend_token are required')
        return 4

    # Cleaning older outputs
    cleanup_old_snapshots(output_dir, retention)

    if client:
        # Managed mode

        # Claim job
        try:
            job = await client.discoveryjob_claim()
            if not job:
                # Nothing to do
                logging.info('No job to claim')
                return 0
        except ValidationError as exc:
            logging.error(exc.message)
            return 7

        job_id = job.id
        idempotency_key = job.idempotency_key
        claim_token = job.claim_token
        inventory = job.inventory
        logging.info('Claimed job %s on %s devices', job_id, len(inventory['all']['hosts']))

        # Register cleanup handler for interrupt signals
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.ensure_future(
                    mark_job_as_failed(client, id=job_id, claim_token=claim_token)
                ),
            )

        # Regurlary send job heartbeat
        job_heartbeat_task = asyncio.create_task(
            send_job_heartbeat(client, id=job_id, claim_token=claim_token)
        )
        background_tasks.add(job_heartbeat_task)
        job_heartbeat_task.add_done_callback(background_tasks.discard)
    elif scan:
        # Stand-alone mode (scan)
        scanner = NetworkScanner(
            ports=[22, 23, 80, 443],
            timeout=0.5,
            concurrency=num_workers * 10,
            credentials=credentials,
            networks=networks,
        )
        hosts = [host async for host in scanner.scan()]
        scanner.save_inventory(hosts, inventory_file)
        return 0
    else:
        # Stand-alone mode (discovery)
        logging.info('Running in stand-alone mode (inventory_file=%s)', inventory_file)
        with open(inventory_file) as fh:
            try:
                inventory = json.load(fh)
            except json.JSONDecodeError:
                logger.error('Invalid JSON in inventory file: %s', inventory_file)
                return 8

    # Initialising Nornir for managed and stand-alone modes
    logger.info('Initialising Nornir (num_workers=%d)', num_workers)
    InventoryPluginRegister.register('NetDocAnsibleInventory', NetDocAnsibleInventory)
    nr = InitNornir(
        runner={
            'plugin': 'threaded',
            'options': {'num_workers': num_workers},
        },
        inventory={
            'plugin': 'NetDocAnsibleInventory',
            'options': {
                'inventory': inventory,
            },
        },
        logging={'enabled': False},
    )

    # Running discovery tasks
    logger.info('Running collector on %d device(s)', len(nr.inventory.hosts))
    results = nr.run(
        task=discovery_task,
        report_path=report_path,
        cmd_timeout=cmd_timeout,
    )
    total_hosts = len(results.values())
    failed_hosts = sum(1 for r in results.values() if r.failed)
    completed_hosts = total_hosts - failed_hosts
    logger.info('Discovery completed on %i/%i hosts', completed_hosts, total_hosts)

    # Closing task (managed mode)
    if client:
        job_status = 'completed'
        # Uploading raw output
        for host_name, result in results.items():
            if result.failed:
                # Skip failed hosts
                continue

            host = nr.inventory.hosts[host_name]
            netdoc_id = host.data.get('netdoc_id')
            raw_outputs = result[0].result
            try:
                await client.discoveryjob_push_discovered_device(
                    id=job_id,
                    data={
                        'canonical_device': netdoc_id,
                        'raw_payload': raw_outputs,
                        'idempotency_key': idempotency_key,
                    },
                    claim_token=claim_token,
                )
            except NetDocError as e:
                job_status = 'failed'
                logger.error(
                    "Upload failed for host '%s': status=%s detail=%s",
                    host_name,
                    e.status_code,
                    e.detail,
                )

        # Close the job
        if completed_hosts == 0:
            job_status = 'failed'
        try:
            await client.discoveryjob_complete(
                id=job_id,
                claim_token=claim_token,
                data={'status': job_status, 'log_messages': log_list_handler.records},
            )
            logging.info(f'Job {job_id} is {job_status}')
        except ValidationError as exc:
            logger.error('Failed to complete job: %s', exc)
            return 10

    return 2 if failed_hosts else 0


def entrypoint() -> int:
    """Execute the collector entrypoint from a console script.

    Returns:
        int: exit code from :func:`main`.
    """
    return asyncio.run(main())


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
