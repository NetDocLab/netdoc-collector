#!/usr/bin/env python3
"""NetDoc discoverer."""

import asyncio
import os
import shutil
import argparse
import logging
import sys
import uuid
import socket
from datetime import datetime
from pathlib import Path
import websockets
import yaml
import json
import netdoc_discovery
from netdoc_discovery.core.mode import managed_mode
from nornir import InitNornir
from nornir.core.plugins.inventory import InventoryPluginRegister

# from netdoc_discovery.core.ansible_inventory import NetDocAnsibleInventory
# from netdoc_discovery.core.tasks import discovery_task
# from netdoc_discovery.core.aggregator import aggregate_and_write

REPORT_PATH_FMT = '%Y%m%d-%H%M%S'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s  %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
    filename='netdoc_discovery.log',
)
logger = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        pass
    return {}


def is_valid_dir(name):
    try:
        datetime.strptime(name, REPORT_PATH_FMT)
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description='NetDoc discoverer')

    # Stand-alone + managed mode
    parser.add_argument('--config', default='config.yaml', help='Path to config.yaml')
    parser.add_argument('--output', default='./output', help='Override output directory')
    parser.add_argument('--cmd-timeout', default=120, help='Override CMD timeout', type=int)  # TODO
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--retention', default=5, help='Override retention', type=int)
    parser.add_argument('--workers', default=5, help='Override worker instances', type=int)

    # Stand-alone mode
    parser.add_argument('--inventory', default='inventory.json', help='Override local inventory file')

    # Managed mode
    parser.add_argument('--url', default='http://localhost:8000', help='Override backend URL')
    parser.add_argument('--verify', default=None, help='Override backend cert verification')
    parser.add_argument('--timeout', default=120, help='Override backend timeout', type=int)
    parser.add_argument('--token', default=None, help='Override API token')

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

    cmd_timeout = args.cmd_timeout or cfg.get('cmd_timeout')
    num_workers = args.workers or cfg.get('workers')
    output_dir = args.output or cfg.get('output', './output')
    retention = args.retention or cfg.get('retention')
    report_path = Path(output_dir) / Path(datetime.now().strftime(REPORT_PATH_FMT))

    # Reading arguments: stand-alone mode
    inventory_file = args.inventory or cfg.get('inventory', None)

    # Reading arguments: managed mode
    agent_id = f"{uuid.uuid4()}@{socket.gethostname()}"
    backend_data = cfg.get('backend', {})
    backend_timeout = args.timeout or backend_data.get("timeout")
    backend_token = os.getenv("NETDOC_TOKEN") or args.token or backend_data.get("token")
    backend_url = args.url or backend_data.get('url')
    backend_verify = args.verify or backend_data.get("verify", True)

    # Checking arguments
    if backend_url and backend_token:
        # Running in managed mode
        logging.info('Running in managed mode (backend_url=%s, agent_id=%s)', backend_url, agent_id)
        return asyncio.run(
            managed_mode(
                backend_url=backend_url,
                backend_token=backend_token,
                backend_verify=backend_verify,
                agent_id=agent_id,
                report_path=report_path,
                num_workers=num_workers,
            )
        )
    elif inventory_file:
        # Running in stand-alone mode
        logging.info('Running in stand-alone mode (inventory_file=%s)', inventory_file)
        with open(inventory_file, 'r') as fh:
            try:
                inventory = json.load(fh)
            except json.JSONDecodeError:
                logger.error('Invalid JSON in inventory file: %s', inventory_file)
                return 1
    else:
        logger.error('At least inventory_file or backend_url and backend_token are required')
        return 1

    # Setting NET_TEXTFSM directory
    ntc_template_path = Path(netdoc_discovery.__file__).parent / Path('ntc_templates')
    logging.info('Using NTC templates from %s', ntc_template_path)
    os.environ["NET_TEXTFSM"] = str(ntc_template_path)

    return 0

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
    # nr = nr.filter(F(hostname="172.25.10.2"))
    logger.info('Running discovery on %d host(s)', len(nr.inventory.hosts))
    results = nr.run(task=discovery_task, report_path=report_path)
    failed_hosts = sum(1 for r in results.values() if r.failed)
    logger.info('Discovery completed (failed on %i hosts)', failed_hosts)

    # Dump results
    netdoc_results = aggregate_and_write(results, report_path)

    # if args.api_token:
    #     from netdoc_discovery.api_sender import send_to_api

    #     send_to_api(
    #         yaml_path=output_path,
    #         api_url=cfg["api"]["url"],
    #         token=args.api_token,
    #         timeout=cfg["api"]["timeout"],
    #     )

    # Cleaming older outputs
    cleanup_old_snapshots(output_dir, retention)

    return 1 if failed_hosts else 0


def cleanup_old_snapshots(output_dir, retention):
    if output_dir and retention:
        snapshot_dirs = sorted(
            [d for d in os.listdir(output_dir) if os.path.isdir(os.path.join(output_dir, d)) and is_valid_dir(d)],
            reverse=True,
        )
        to_delete = snapshot_dirs[retention:]
        for d in to_delete:
            logging.info("Deleted snapshot directory %s", d)
            shutil.rmtree(os.path.join(output_dir, d))


if __name__ == '__main__':
    sys.exit(main())
