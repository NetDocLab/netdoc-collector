"""Unit tests for NetDocAnsibleInventory."""

import json
import stat

import pytest

from netdoc_collector.core.ansible_inventory import NetDocAnsibleInventory

# ─────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────

SAMPLE_INVENTORY: dict = {
    '_meta': {
        'hostvars': {
            'router-01': {
                'ansible_host': '192.168.1.1',
                'ansible_user': 'admin',
                'ansible_password': 'secret',
                'ansible_port': 22,
                'netmiko_device_type': 'cisco_ios',
                'netdoc_plugin': 'netmiko:cisco:ios:ssh',
            },
            'switch-01': {
                'ansible_host': '192.168.1.2',
                'ansible_user': 'admin',
                'ansible_password': 'secret',
                'ansible_port': 22,
                'netmiko_device_type': 'hp_procurve',
                'netdoc_plugin': 'netmiko:hp:procurve:ssh',
            },
        }
    },
    'all': {
        'hosts': ['router-01', 'switch-01'],
    },
    'routers': {
        'hosts': ['router-01'],
    },
    'switches': {
        'hosts': ['switch-01'],
    },
}


@pytest.fixture
def inventory_json_file(tmp_path) -> str:
    """Write SAMPLE_INVENTORY to a non-executable JSON file and return the path."""
    path = tmp_path / 'inventory.json'
    path.write_text(json.dumps(SAMPLE_INVENTORY))
    # Ensure the file is NOT executable
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return str(path)


@pytest.fixture
def inventory_executable_file(tmp_path) -> str:
    """Write SAMPLE_INVENTORY to an executable file and return the path."""
    path = tmp_path / 'inventory_exec.json'
    path.write_text(json.dumps(SAMPLE_INVENTORY))
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    return str(path)


class TestInitFromDict:
    def test_accepts_dict(self):
        inv = NetDocAnsibleInventory(SAMPLE_INVENTORY)
        assert inv.inventory == SAMPLE_INVENTORY

    def test_inventory_attribute_is_same_object(self):
        inv = NetDocAnsibleInventory(SAMPLE_INVENTORY)
        assert inv.inventory is SAMPLE_INVENTORY

    def test_logs_dict_message(self, caplog):
        import logging

        with caplog.at_level(logging.INFO):
            NetDocAnsibleInventory(SAMPLE_INVENTORY)
        assert 'dict' in caplog.text.lower()


class TestInitFromJsonFile:
    def test_accepts_json_file(self, inventory_json_file):
        inv = NetDocAnsibleInventory(inventory_json_file)
        assert inv.inventory == SAMPLE_INVENTORY

    def test_loads_correct_hosts(self, inventory_json_file):
        inv = NetDocAnsibleInventory(inventory_json_file)
        assert 'router-01' in inv.inventory['_meta']['hostvars']

    def test_logs_json_file_message(self, inventory_json_file, caplog):
        import logging

        with caplog.at_level(logging.INFO):
            NetDocAnsibleInventory(inventory_json_file)
        assert 'json' in caplog.text.lower()


class TestInitFromExecutableFile:
    def test_executes_script_and_parses_output(self, tmp_path):
        script = tmp_path / 'inv.sh'
        script.write_text(f"#!/bin/sh\necho '{json.dumps(SAMPLE_INVENTORY)}'")
        script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        inv = NetDocAnsibleInventory(str(script))
        assert inv.inventory == SAMPLE_INVENTORY

    def test_raises_on_nonzero_exit(self, tmp_path):
        script = tmp_path / 'bad.sh'
        script.write_text('#!/bin/sh\nexit 1')
        script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        with pytest.raises(ValueError, match='exited with code'):
            NetDocAnsibleInventory(str(script))

    def test_raises_on_invalid_json_output(self, tmp_path):
        script = tmp_path / 'bad_json.sh'
        script.write_text("#!/bin/sh\necho 'not json'")
        script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        with pytest.raises(ValueError, match='invalid JSON'):
            NetDocAnsibleInventory(str(script))


class TestInitInvalidInput:
    def test_raises_on_nonexistent_path(self):
        with pytest.raises(ValueError, match='not valid'):
            NetDocAnsibleInventory('/nonexistent/path/inventory.json')

    def test_raises_on_integer(self):
        with pytest.raises(ValueError, match='not valid'):
            NetDocAnsibleInventory(42)  # type: ignore[arg-type]

    def test_raises_on_none(self):
        with pytest.raises(ValueError, match='not valid'):
            NetDocAnsibleInventory(None)  # type: ignore[arg-type]

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError, match='not valid'):
            NetDocAnsibleInventory('')

    def test_raises_on_directory(self, tmp_path):
        with pytest.raises(ValueError, match='not valid'):
            NetDocAnsibleInventory(str(tmp_path))


class TestLoad:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.inv = NetDocAnsibleInventory(SAMPLE_INVENTORY)
        self.result = self.inv.load()

    def test_returns_inventory_object(self):
        from nornir.core.inventory import Inventory

        assert isinstance(self.result, Inventory)

    def test_all_group_exists(self):
        assert 'all' in self.result.groups

    def test_hosts_count(self):
        assert len(self.result.hosts) == 2

    def test_host_names(self):
        assert 'router-01' in self.result.hosts
        assert 'switch-01' in self.result.hosts


class TestLoadGroups:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.result = NetDocAnsibleInventory(SAMPLE_INVENTORY).load()

    def test_extra_groups_exist(self):
        assert 'routers' in self.result.groups
        assert 'switches' in self.result.groups

    def test_router_in_routers_group(self):
        host_group_names = [g.name for g in self.result.hosts['router-01'].groups]
        assert 'routers' in host_group_names

    def test_switch_not_in_routers_group(self):
        host_group_names = [g.name for g in self.result.hosts['switch-01'].groups]
        assert 'routers' not in host_group_names


class TestLoadHostAttributes:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.result = NetDocAnsibleInventory(SAMPLE_INVENTORY).load()
        self.host = self.result.hosts['router-01']

    def test_hostname(self):
        assert self.host.hostname == '192.168.1.1'

    def test_username(self):
        assert self.host.username == 'admin'

    def test_password(self):
        assert self.host.password == 'secret'

    def test_port(self):
        assert self.host.port == 22

    def test_platform(self):
        assert self.host.platform == 'cisco_ios'

    def test_data_contains_host_vars(self):
        assert self.host.data.get('netdoc_plugin') == 'netmiko:cisco:ios:ssh'

    def test_connection_options_empty(self):
        assert self.host.connection_options == {}


class TestLoadMissingHostVars:
    def test_missing_optional_fields_default_to_none(self):
        sparse_inventory = {
            '_meta': {'hostvars': {'bare-host': {}}},
            'all': {'hosts': ['bare-host']},
        }
        result = NetDocAnsibleInventory(sparse_inventory).load()
        host = result.hosts['bare-host']
        assert host.hostname is None
        assert host.username is None
        assert host.password is None
        assert host.port is None
        assert host.platform is None
