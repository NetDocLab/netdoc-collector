"""Ansible inventory support for Nornir.

This module loads inventory data from JSON files, dictionaries, or executable
inventory scripts and exposes it to Nornir as an inventory object.
"""

import json
import logging
import os
import subprocess  # nosec B404 - required to run local dynamic inventory

from nornir.core.inventory import (
    ConnectionOptions,
    Defaults,
    Group,
    Groups,
    Host,
    Hosts,
    Inventory,
    ParentGroups,
)


class NetDocAnsibleInventoryError(Exception):
    pass


class NetDocAnsibleInventory:
    def __init__(
        self,
        inventory: str | dict,
    ) -> None:
        """Initialize the inventory plugin from a file, dictionary, or executable script.

        Args:
            inventory: path to an Ansible JSON file, executable inventory script,
                or an in-memory inventory dictionary.
        """
        if isinstance(inventory, dict):
            logging.info('Reading inventory from dict')
            self.inventory = inventory
        elif isinstance(inventory, str) and os.path.isfile(inventory):
            if os.access(inventory, os.X_OK):
                logging.info('Reading inventory from executable file')
                self.inventory = self._run_executable(inventory)
            else:
                logging.info('Reading inventory from JSON file')
                with open(inventory) as fh:
                    self.inventory = json.load(fh)
        else:
            raise NetDocAnsibleInventoryError('Inventory is not valid')

        # Inventory format validation occurs during Nornir host construction.

    @staticmethod
    def _run_executable(path: str) -> dict:
        """Execute a dynamic inventory script and parse its JSON output.

        Args:
            path: path to the executable inventory script.

        Returns:
            Parsed inventory dict.

        Raises:
            ValueError: if the process exits with a non-zero code or stdout is not valid JSON.
        """
        try:
            result = subprocess.run(  # nosec B603 - inventory must be executed, shell=False is intentional and safer than shell=True
                [path],
                capture_output=True,
                shell=False,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ValueError(
                f"Inventory script '{path}' exited with code {e.returncode}: {e.stderr.strip()}"
            ) from e

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise ValueError(f"Inventory script '{path}' returned invalid JSON: {e}") from e

    def load(self) -> Inventory:
        """Load the current inventory into a Nornir inventory object."""
        defaults = Defaults()
        hosts = Hosts()
        groups = Groups()

        # Add "all" group
        groups['all'] = Group('all')

        # Load groups from top-level keys, excluding reserved Ansible keys
        _RESERVED_KEYS = {'_meta', 'all'}
        for group_name in self.inventory:
            if group_name not in _RESERVED_KEYS:
                groups[group_name] = Group(group_name)

        # Load hosts
        for inventory_hostname, host_data in self.inventory['_meta']['hostvars'].items():
            connection_options: dict[str, ConnectionOptions] = {}

            # Collect groups this host belongs to
            host_groups = ParentGroups()
            for group_name, group_data in self.inventory.items():
                if group_name not in _RESERVED_KEYS and inventory_hostname in group_data.get(
                    'hosts', []
                ):
                    host_groups.append(groups[group_name])

            # Configure privilege escalation
            ansible_become = host_data.get('ansible_become', '')
            ansible_become_password = host_data.get('ansible_become_password', '')
            connection_options = {}
            if ansible_become and ansible_become_password:
                connection_options['netmiko'] = ConnectionOptions(
                    extras={'secret': ansible_become_password}
                    if ansible_become == 'yes' and ansible_become_password
                    else {}
                )

            hosts[inventory_hostname] = Host(
                name=inventory_hostname,
                hostname=host_data.get('ansible_host'),
                username=host_data.get('ansible_user'),
                password=host_data.get('ansible_password'),
                port=host_data.get('ansible_port'),
                platform=host_data.get('netmiko_device_type'),
                data=host_data,
                groups=host_groups,
                connection_options=connection_options,
            )

        return Inventory(hosts=hosts, groups=groups, defaults=defaults)
