import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.conftest import _get_ios_device, skip_ios_device_tests

testbed = _get_ios_device()


class TestStandAloneScan:
    """Execute the collector as a subprocess against the Cisco device."""

    @pytest.fixture()
    def workdir(self, tmp_path):
        config = {
            'cmd_timeout': 10,
            'output': './output',
            'retention': 2,
            'workers': 2,
            'inventory': './inventory.json',
            'backend': {
                'url': 'http://localhost:8000/',
                'verify': False,
                'timeout': 120,
                'token': None,
            },
        }
        (tmp_path / 'config.yaml').write_text(yaml.dump(config))
        (tmp_path / 'secrets.yaml').write_text(
            yaml.dump({'credentials': testbed['scan']['credentials']})
        )
        (tmp_path / 'output').mkdir()
        return tmp_path

    def _run(self, workdir: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                '-m',
                'netdoc_collector',
                '-s',
                '-n',
                str(testbed['scan']['networks'][0]),
                '-p',
                str(workdir / 'secrets.yaml'),
                '-i',
                str(workdir / 'inventory.json'),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(workdir),
        )

    @pytest.mark.skipif(skip_ios_device_tests() is True, reason='Skip device related tests')
    def test_scan(self, workdir):

        r = self._run(workdir)
        assert r.returncode == 0

        # Verify inventory
        with open('inventory.json') as fh:
            inventory = json.load(fh)

        ansible_host = testbed['collector']['address']
        ansible_user = testbed['collector']['username']
        ansible_password = testbed['collector']['password']

        # Host
        assert '_meta' in inventory
        assert 'hostvars' in inventory['_meta']
        assert ansible_host in inventory['_meta']['hostvars']
        result = inventory['_meta']['hostvars'][ansible_host]
        assert result.get('ansible_host') == ansible_host
        assert result.get('ansible_user') == ansible_user
        assert result.get('ansible_password') == ansible_password
        assert result.get('ansible_port') == 22
        assert result.get('netdoc_plugin') == 'netmiko:cisco:ios:ssh'
        assert result.get('netmiko_device_type') == 'cisco_ios'

        # Group all
        assert 'all' in inventory
        assert 'hosts' in inventory['all']
        assert len(inventory['all']['hosts']) == 1
