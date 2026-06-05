#!/usr/bin/env python3
"""NetDoc discoverer."""

import argparse
import asyncio
import getpass
import ipaddress
import json
import logging
import os
import socket
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import netdoc_sdk
from netdoc_sdk.client import NetDocClient
from netdoc_sdk.exceptions import NetDocError, ValidationError
from nornir import InitNornir
from nornir.core.plugins.inventory import InventoryPluginRegister

from netdoc_collector.core.ansible_inventory import NetDocAnsibleInventory
from netdoc_collector.core.scanner import NetworkScanner
from netdoc_collector.core.tasks import discovery_task
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
    claim_token = None
    client = None
    collector_name = f'{getpass.getuser()}@{socket.getfqdn()}'
    collector_version = version('netdoc-collector')
    idempotency_key = None
    job_id = None
    backend_data = cfg.get('backend', {})
    backend_timeout = args.timeout or backend_data.get('timeout') or 120
    backend_token = os.getenv('NETDOC_TOKEN') or args.token or backend_data.get('token')
    backend_url = args.url or backend_data.get('url', 'http://localhost:8000')
    # backend_verify = args.verify or backend_data.get("verify", True)  # TODO

    # Define managed or stand alone mode
    managed = False
    if backend_url and backend_token:
        managed = True

    if scan:
        logging.info(f'Running in scan mode (managed={managed})')
        networks = []
        if not input_networks:
            # Add local networks
            for iface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family != socket.AF_INET:
                        continue

                    network = ipaddress.IPv4Network(f'{addr.address}/{addr.netmask}', strict=False)

                    if network.is_loopback:
                        # Esclude loopback
                        continue

                    if not network.is_private:
                        # Inlcude private networks only
                        continue

                    networks.append(network)
        else:
            for input_network in input_networks:
                try:
                    network = ipaddress.IPv4Network(input_network, strict=False)
                except ipaddress.NetmaskValueError:
                    logging.error(f'Network {input_network} is invalid')
                    sys.exit(1)
                networks.append(network)

        if not managed:
            # Load credentials from secrets.yaml
            secrets = load_config('secrets.yaml')
            credentials = secrets.get('credentials', {})
            if not credentials:
                logging.error('No credential found')
                sys.exit(2)

        scanner = NetworkScanner(
            ports=[22, 23, 80, 443],
            timeout=0.5,
            concurrency=num_workers * 10,
            credentials=credentials,
        )
        async for host in scanner.scan(networks):
            print('---', host.ip, host.open_ports, host.device_type)
        sys.exit(0)

    # Checking arguments
    if backend_url and backend_token:
        # Running in managed mode
        managed_mode = True
        logging.info(
            'Running in managed mode (backend_url=%s, collector_name=%s)',
            backend_url,
            collector_name,
        )
        client = NetDocClient(base_url=backend_url, token=backend_token, timeout=backend_timeout)

        # Heartbeat (login test)
        try:
            await client.collectors_heartbeat_create(
                data={'name': collector_name, 'version': collector_version}
            )
            logging.info('Collector is logged in')
        except netdoc_sdk.exceptions.ConnectionError as exc:
            logging.error(exc)
            return 1

        # Claim
        job = await client.discovery_jobs_claim_create()
        if not job:
            # Nothing to do
            logging.info('No job to claim')
            return 0

        job_id = job.id
        idempotency_key = job.idempotency_key
        claim_token = job.claim_token
        inventory = job.inventory
        logging.info('Claimed job %s on %s devices', job_id, len(job.inventory['all']['hosts']))

    elif inventory_file:
        # Running in stand-alone mode
        managed_mode = False
        logging.info('Running in stand-alone mode (inventory_file=%s)', inventory_file)
        with open(inventory_file) as fh:
            try:
                inventory = json.load(fh)
            except json.JSONDecodeError:
                logger.error('Invalid JSON in inventory file: %s', inventory_file)
                return 1
    else:
        logger.error('At least inventory_file or backend_url and backend_token are required')
        return 1

    # Initialising Nornir
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
    if managed_mode:
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
                await client.discovery_push_discovered_device_create(
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
            await client.discovery_jobs_complete_create(
                id=job_id,
                claim_token=claim_token,
                data={'status': job_status, 'log_messages': log_list_handler.records},
            )
            logging.info(f'Job {job_id} is {job_status}')
        except ValidationError as exc:
            logger.error('Failed to complete job: %s', exc)
            return 2

    # Cleaning older outputs
    cleanup_old_snapshots(output_dir, retention)

    return 1 if failed_hosts else 0


def entrypoint() -> int:
    return asyncio.run(main())


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
