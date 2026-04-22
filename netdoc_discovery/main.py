#!/usr/bin/env python3
"""NetDoc discoverer."""

import os
import shutil
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
import yaml
import netdoc_discovery
from nornir import InitNornir
from nornir.core.plugins.inventory import InventoryPluginRegister
from netdoc_discovery.core.ansible_inventory import NetDocAnsibleInventory
from netdoc_discovery.core.tasks import discovery_task
from netdoc_discovery.core.aggregator import aggregate_and_write

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
        datetime.strptime(name, '%Y-%m-%d-%H:%M:%S')
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description='NetDoc discoverer')
    parser.add_argument('--config', default='config.yaml', help='Path to config.yaml')
    parser.add_argument('--inventory', default=None, help='Override local inventory file')
    parser.add_argument('--output', default=None, help='Override output directory')
    parser.add_argument('--retention', default=5, help='Override retention')
    parser.add_argument('--workers', default=None, help='Override worker instances')
    parser.add_argument('--url', default=None, help='Override backend URL')
    parser.add_argument('--verify', default=None, help='Override backend cert verification')
    parser.add_argument('--timeout', default=None, help='Override backend timeout')
    parser.add_argument('--cmd-timeout', default=None, help='Override CMD timeout')  # TODO
    parser.add_argument('--token', default=None, help='Override API token')
    args = parser.parse_args()

    # Reading arguments
    cfg = load_config(args.config)
    inventory_file = args.inventory or cfg.get('inventory', None)
    output_dir = args.output or cfg.get('output', './output')
    retention = args.retention or cfg.get('retention')
    num_workers = args.workers or cfg.get('workers', 5)
    backend_data = cfg.get('backend', {})
    backend_url = args.url or backend_data.get('url')
    # backend_verify = args.verify or backend_data.get("verify", True)
    # backend_timeout = args.timeout or backend_data.get("timeout", 10)
    # backend_token = os.getenv("NETDOC_TOKEN") or args.token or backend_data.get("token")

    # Checking arguments
    if backend_url:
        # Using NetDoc backend
        logging.info('Running in client-server mode (backend_url=%s)', backend_url)
        inventory = {}
    elif inventory_file:
        # Running stand-alone
        logging.info('Running in stand-alone mode (inventory_file=%s)', inventory_file)
        inventory = inventory_file
        now = datetime.now()
        report_path = Path(output_dir) / Path(now.strftime('%Y%m%d-%H%M%S'))
    else:
        logger.error('At least inventory_file or backend_url is required')
        sys.exit(1)

    # Setting NET_TEXTFSM directory
    ntc_template_path = Path(netdoc_discovery.__file__).parent / Path('ntc_templates')
    logging.info('Using NTC templates from %s', ntc_template_path)
    os.environ["NET_TEXTFSM"] = str(ntc_template_path)

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
    if output_dir and retention:
        snapshot_dirs = sorted(
            [d for d in os.listdir(output_dir) if os.path.isdir(os.path.join(output_dir, d)) and is_valid_dir(d)],
            reverse=True,
        )
        to_delete = snapshot_dirs[retention:]
        for d in to_delete:
            logging.info("Deleted snapshot directory %s", d)
            shutil.rmtree(os.path.join(output_dir, d))

    return 1 if failed_hosts else 0


if __name__ == '__main__':
    sys.exit(main())
