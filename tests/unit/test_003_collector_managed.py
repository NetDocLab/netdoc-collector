"""Unit tests for NetworkScanner (stand alone)."""

import logging
import os
import uuid
from unittest.mock import patch

import pytest
from apps.core.context import set_current_tenant
from apps.core.models import LogRecord, Tenant
from apps.discovery.models import Collector, Credential, DiscoveryJob, RawOutput
from apps.discovery.services import DiscoveryRunService
from apps.inventory.models import CanonicalDevice, Device, Site
from conftest import FailingVendorPlugin, FakeVendorPlugin, _workdir
from django.contrib.auth import get_user_model
from nornir.core.plugins.inventory import InventoryPluginRegister
from rest_framework.authtoken.models import Token

from netdoc_collector.core.ansible_inventory import NetDocAnsibleInventory
from netdoc_collector.main import main as netdoc_collector_main


@pytest.mark.django_db(databases=['default', 'logs'])
class TestCollectorManaged:
    """Managed collector."""

    @pytest.fixture(autouse=True)
    def setup(self, live_server, scanner, tmp_path):
        InventoryPluginRegister.register('NetDocAnsibleInventory', NetDocAnsibleInventory)

        admin_username = 'conftest-admin'
        admin_password = 'af7fbd06acd9a4923f63edad362dc774'
        collector_username = 'conftest-collector'
        collector_password = '986629a7ca89202a3ef2ae1dd9d5fb37'

        # Create tenant
        tenant = Tenant.objects.create(name='conftest-tenant')
        set_current_tenant(tenant)

        # Create collector user
        User = get_user_model()
        admin_user = User.objects.create_user(
            username=admin_username,
            password=admin_password,
            role='admin',
            tenant=tenant,
        )
        collector_user = User.objects.create_user(
            username=collector_username,
            password=collector_password,
            role='collector',
            tenant=tenant,
        )
        token, _ = Token.objects.get_or_create(user=collector_user)

        # Create site
        site = Site.objects.create(name='Conftest Site', is_default=True)

        # Create credential
        credential = Credential.objects.create(
            label='Conftest Credential', username='admin', password='admin'
        )

        # Create and enable collector
        collector = Collector.objects.create(
            name='collector@conftest',
            version='0.0.0',
            is_active=True,
            user=collector_user,
        )

        # Create canonical device
        CanonicalDevice.objects.create(
            label='router1.example.com',
            identifiers={'hostname': 'router1'},
            is_discoverable=True,
            credential=credential,
            discovery_mode='netmiko:cisco:ios:ssh',
            site=site,
            tenant=tenant,
        )

        # Create run
        run = DiscoveryRunService.create_run(requested_by=admin_user, tenant=tenant)
        snapshot = run.snapshot
        job = DiscoveryJob.objects.unfiltered().get(collector=collector, run=run)
        self.SNAPSHOT = snapshot
        claim_token = uuid.uuid4()
        job.claim_token = claim_token
        job.save(update_fields=['claim_token'])

        self.TOKEN = token.key
        self.URL = live_server.url

    @patch('netdoc_collector.core.tasks.get_plugin')
    def test_collector(self, mock_get_plugin, tmp_path, caplog, monkeypatch):
        caplog.set_level(logging.INFO)
        _workdir(tmp_path, dump_config=False, dump_inventory=False, dump_secrets=False)
        output_dir = tmp_path / 'output'

        # Mock result
        mock_get_plugin.side_effect = lambda **kwargs: FakeVendorPlugin(**kwargs)

        monkeypatch.chdir(tmp_path)
        with patch(
            'sys.argv',
            [
                'collector',
                '-o',
                str(output_dir),
                '-u',
                self.URL,
                '--token',
                self.TOKEN,
            ],
        ):
            result = netdoc_collector_main()
        # Check result
        assert result == 0, caplog.text

        # Check inventory
        assert not os.path.isfile(tmp_path / 'inventory.json')

        # Check output
        assert os.path.isdir(tmp_path / 'output')
        directories = [p for p in (tmp_path / 'output').iterdir() if p.is_dir()]
        assert len(directories) == 1
        assert os.path.isdir(directories[0] / 'router1.example.com')
        assert os.path.isfile(directories[0] / 'router1.example.com' / 'show-version.raw')

        # Check database
        raw_outputs = RawOutput.objects.all()
        assert len(raw_outputs) == 1
        devices = Device.objects.filter(snapshot=self.SNAPSHOT)
        assert len(devices) == 1
        logs = LogRecord.objects.all()
        assert len(logs) > 10

    @patch('netdoc_collector.core.tasks.get_plugin')
    def test_collector_fail(self, mock_get_plugin, tmp_path, caplog, monkeypatch):
        caplog.set_level(logging.INFO)
        _workdir(tmp_path, dump_config=False, dump_inventory=False, dump_secrets=False)
        output_dir = tmp_path / 'output'

        # Mock result
        mock_get_plugin.side_effect = lambda **kwargs: FailingVendorPlugin(**kwargs)

        monkeypatch.chdir(tmp_path)
        with patch(
            'sys.argv',
            [
                'collector',
                '-o',
                str(output_dir),
                '-u',
                self.URL,
                '--token',
                self.TOKEN,
            ],
        ):
            result = netdoc_collector_main()
        # Check result
        assert result == 2, caplog.text

        # Check inventory
        assert not os.path.isfile(tmp_path / 'inventory.json')

        # Check output
        assert os.path.isdir(tmp_path / 'output')
        directories = [p for p in (tmp_path / 'output').iterdir() if p.is_dir()]
        assert len(directories) == 1
        assert os.path.isdir(directories[0] / 'router1.example.com')

        # Check database
        raw_outputs = RawOutput.objects.all()
        assert len(raw_outputs) == 0
        devices = Device.objects.filter(snapshot=self.SNAPSHOT)
        assert len(devices) == 0

        logs = LogRecord.objects.all()
        assert len(logs) > 10
