"""nornir_ansible.inventory.ansible"""

import os
import json
import logging
from nornir.core.inventory import (
    Inventory,
    Host,
    Hosts,
    Group,
    Groups,
    ParentGroups,
    Defaults,
)


class NetDocAnsibleInventory:
    def __init__(
        self,
        inventory: str | dict,
    ) -> None:
        """
        Ansible Dynamic Inventory plugin supporting JSON files, dict and executable files.

        Arguments:
            inventory: Path to valid Ansible JSON file, Ansible dynamic inventory, dict

        """
        if isinstance(inventory, dict):
            # Inventory is already in dict format
            logging.info('Reading inventory from dict')
            self.inventory = inventory
        elif isinstance(inventory, str) and os.path.isfile(inventory):
            # Inventory is a file
            if os.access(inventory, os.X_OK):
                # Inventory is an executable file
                logging.info('Reading inventory from executable file')
                # TODO
                pass
            else:
                # Inventory is a non executable file
                logging.info('Reading inventory from JSON file')
                with open(inventory) as fh:
                    self.inventory = json.load(fh)
        else:
            raise ValueError('Inventory is not valid')

        # TODO: should validate JSON format and trigger errors

    def load(self) -> Inventory:
        """Load items from remote API."""
        defaults = Defaults()
        hosts = Hosts()
        groups = Groups()

        # Add "all" group
        groups['all'] = Group('all')

        # Load hosts
        for inventory_hostname, host_data in self.inventory['_meta'][
            'hostvars'
        ].items():
            #     # for discoverable in [discoverables]:
            #     # credential = discoverable.credential
            #     # Add hosts discoverable via Netmiko
            #     # platform = DiscoveryModeChoices.MODES.get(discoverable.mode).get("platform")
            #     # Pass parameters between NetDoc and Nornir
            #     # data = {
            #     #     "site_id": discoverable.site.pk,
            #     #     "site": discoverable.site.slug,
            #     #     "verify_cert": credential.verify_cert,
            #     # }
            #     data = {
            #         "aaa": "bbb",
            #         "ccc": "ddd",
            #     }

            #     # host_key = discoverable.address
            #     # host_groups = [platform, f'site-{data["site"]}']
            #     host_groups = ["netmiko", "cisco_ios"]

            #     # Create additional options
            #     # netmiko_extras = {}
            #     # if credential.enable_password:
            #     #     extras["secret"] = credential.get_secrets().get("enable_password")
            #     # connection_options = {"netmiko": ConnectionOptions(extras=netmiko_extras)}
            #     connection_options = {}

            hosts[inventory_hostname] = Host(
                name=inventory_hostname,
                hostname=host_data.get('ansible_host'),
                username=host_data.get('ansible_user'),
                password=host_data.get('ansible_password'),
                port=22,
                # platform=host_data.get("netdoc_discovery_type"),
                platform=host_data.get('netmiko_device_type'),
                data=host_data,
                groups=ParentGroups(),
                # connection_options=connection_options,
            )  # IP is the key used in AggregatedResults

            #     # Add groups
            # for host_group in host_groups:
            #     if host_group not in dict(groups):
            #         groups[host_group] = Group(host_group)
            #     hosts[inventory_hostname].groups.append(Group(host_group))

        return Inventory(hosts=hosts, groups=groups, defaults=defaults)
