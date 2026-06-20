import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from apps.inventory.models import Device
from asgiref.sync import sync_to_async

from tests.conftest import _get_ios_device, skip_ios_device_tests

testbed = _get_ios_device()


class TestManagedCollector:
    """Execute the collector as a subprocess against the Cisco device."""

    @pytest.fixture()
    def workdir(self, tmp_path):
        config = {
            'cmd_timeout': 10,
            'output': './output',
            'retention': 2,
            'workers': 2,
            'backend': {
                'url': 'http://localhost:8000/',
                'verify': False,
                'timeout': 120,
                'token': None,
            },
        }
        (tmp_path / 'config.yaml').write_text(yaml.dump(config))
        return tmp_path

    def _run(self, workdir: Path, url=None, token=None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                '-m',
                'netdoc_collector',
                '-u',
                url,
                '--token',
                token,
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(workdir),
        )

    @pytest.mark.skipif(skip_ios_device_tests() is True, reason='Skip device related tests')
    @pytest.mark.django_db(transaction=True)
    async def test_managed_collector(self, workdir, live_server, admin_client, collector_client):
        ansible_host = testbed['collector']['address']
        ansible_user = testbed['collector']['username']
        ansible_password = testbed['collector']['password']

        # Create credential
        credential = await admin_client.credential_add(
            label='test-credential', username=ansible_user, password=ansible_password
        )

        # Create canonical device
        await admin_client.canonicaldevice_add(
            label='test-canonical-device',
            identifiers={'hostname': 'sw1'},
            mgmt_address=ansible_host,
            discovery_mode='netmiko:cisco:ios:ssh',
            is_discoverable=True,
            credential=credential.id,
        )

        # Create collector (heartbeat)
        r = self._run(workdir, url=live_server.url, token=collector_client.token)
        assert r.returncode != 0  # Non active collectors registers but cannot claim jobs

        # Activate collector
        collectors = await admin_client.collector_list()
        assert collectors.count == 1
        collector = collectors.results[0]
        await admin_client.collector_update(collector.id, is_active=True)

        # Create run
        run = await admin_client.discovery_add()

        # Run the collector
        r = self._run(workdir, url=live_server.url, token=collector_client.token)
        assert r.returncode == 0

        # Verify data on backend
        run_result = await admin_client.discovery_get(run.id)
        assert run_result.status.value == 'completed'

        jobs = await admin_client.discovery_jobs(run.id)
        assert jobs.count == 1
        job = jobs.results[0]
        assert job.status.value == 'completed'

        logs = await admin_client.discoveryjob_logs(id=job.id)
        assert logs.count == 1

        for log in logs.results:
            assert log.status.value == 'parsed'

        # TODO: use API to check devices
        devices = await sync_to_async(lambda: list(Device.objects.unfiltered().all()))()
        assert len(devices) == 1
