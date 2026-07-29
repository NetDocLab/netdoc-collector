"""Unit tests for NetworkScanner (stand alone)."""

import json
import os
from unittest.mock import patch

from conftest import FakeVendorPlugin, _run, _workdir


class TestCollectorStandalone:
    """Stand alone collector."""

    @patch('netdoc_collector.core.tasks.get_plugin')
    def test_collector(self, mock_get_plugin, tmp_path):
        # Mock result
        mock_get_plugin.side_effect = lambda **kwargs: FakeVendorPlugin(**kwargs)

        _workdir(tmp_path)
        result = _run(tmp_path)

        # Check result
        assert result.returncode == 0, result.stderr

        # Check inventory
        inventory = json.loads((tmp_path / 'inventory.json').read_text())
        assert '10.0.0.1' in inventory['_meta']['hostvars']
        assert inventory['all']['hosts'] == ['10.0.0.1']
        hostvars = inventory['_meta']['hostvars']['10.0.0.1']
        assert hostvars['ansible_host'] == '10.0.0.1'
        assert hostvars['ansible_user'] == 'admin'
        assert hostvars['ansible_password'] == 'admin'
        assert hostvars['ansible_port'] == 22
        assert hostvars['netdoc_plugin'] == 'netmiko:cisco:ios:ssh'
        assert hostvars['netmiko_device_type'] == 'cisco_ios'

        # Check output
        assert os.path.isdir(tmp_path / 'output')
        directories = [p for p in (tmp_path / 'output').iterdir() if p.is_dir()]
        assert len(directories) == 1
        assert os.path.isdir(directories[0] / '10.0.0.1')
