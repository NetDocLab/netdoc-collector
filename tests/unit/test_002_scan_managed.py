"""Unit tests for NetworkScanner (managed)."""

import uuid
from unittest.mock import patch

import pytest
from apps.core.context import set_current_tenant
from apps.core.models import Tenant
from apps.discovery.models import Collector, Credential, DiscoveryJob, RawOutput
from apps.discovery.services import DiscoveryRunService
from apps.inventory.models import Device, Site
from conftest import FailingVendorPlugin, FakeVendorPlugin
from django.contrib.auth import get_user_model
from netdoc_sdk.client import NetDocSyncClient
from nornir.core.plugins.inventory import InventoryPluginRegister
from rest_framework.authtoken.models import Token

from netdoc_collector.core.ansible_inventory import NetDocAnsibleInventory
from netdoc_collector.core.scanner import NetworkScanner


class TestScanManaged:
    """Managed scan upload data to the backend."""

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

        # Create client
        client = NetDocSyncClient(
            base_url=live_server.url,
            token=token.key,
            verify=False,
        )

        # Create site
        Site.objects.create(name='Conftest Site', is_default=True)

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

        # Create run
        run = DiscoveryRunService.create_run(requested_by=admin_user, tenant=tenant)
        snapshot = run.snapshot
        job = DiscoveryJob.objects.unfiltered().get(collector=collector, run=run)

        crendetials = [
            {
                'id': str(credential.id),
                'username': credential.username,
                'password': credential.password,
            }
        ]
        self.SNAPSHOT = snapshot
        claim_token = uuid.uuid4()
        job.claim_token = claim_token
        job.save(update_fields=['claim_token'])

        scanner.credentials = crendetials
        scanner.report_path = tmp_path
        scanner.client = client
        scanner.claim_token = str(claim_token)
        scanner.job_id = str(job.id)
        scanner.idempotency_key = str(job.idempotency_key)
        self.SCANNER = scanner

    @patch.object(NetworkScanner, '_check_port', return_value=False)
    def test_scan_unreachable_host(self, _mock_check_port):
        scanner = self.SCANNER
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = scanner.summarize_discovery(hosts)

        assert len(hosts) == 0
        assert scan_completed_hosts == 0
        assert scan_failed_hosts == 0

    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_unsupported(self, _mock_check_port, mock_ssh_detect):
        # Mock result
        mock_ssh_detect.return_value.autodetect.return_value = 'fake_vendor'

        scanner = self.SCANNER
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = scanner.summarize_discovery(hosts)

        assert len(hosts) == 0
        assert scan_completed_hosts == 0
        assert scan_failed_hosts == 0

    @patch('netdoc_collector.core.tasks.get_plugin')
    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_failed(self, _mock_check_port, mock_ssh_detect, mock_get_plugin):
        # Mock result
        mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'
        mock_get_plugin.side_effect = lambda **kwargs: FailingVendorPlugin(**kwargs)

        scanner = self.SCANNER
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = scanner.summarize_discovery(hosts)
        scanner.complete(hosts)

        assert len(hosts) == 1
        assert scan_completed_hosts == 0
        assert scan_failed_hosts == 1

        raw_outputs = RawOutput.objects.all()
        assert len(raw_outputs) == 0
        devices = Device.objects.filter(snapshot=self.SNAPSHOT)
        assert len(devices) == 0

    @patch('netdoc_collector.core.tasks.get_plugin')
    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_discovery(self, _mock_check_port, mock_ssh_detect, mock_get_plugin):
        # Mock result
        mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'
        mock_get_plugin.side_effect = lambda **kwargs: FakeVendorPlugin(**kwargs)

        scanner = self.SCANNER
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = scanner.summarize_discovery(hosts)
        scanner.complete(hosts)

        assert len(hosts) == 1
        assert scan_completed_hosts == 1
        assert scan_failed_hosts == 0

        raw_outputs = RawOutput.objects.all()
        assert len(raw_outputs) == 1
        devices = Device.objects.filter(snapshot=self.SNAPSHOT)
        assert len(devices) == 1
