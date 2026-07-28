"""Unit tests for NetworkScanner (managed)."""

import ipaddress
from unittest.mock import MagicMock, patch

import pytest
from apps.core.models import Tenant
from apps.discovery.models import Collector, Credential
from apps.inventory.models import Site
from conftest import _fake_discovery_result
from django.contrib.auth import get_user_model
from netdoc_sdk.client import NetDocSyncClient
from nornir.core.plugins.inventory import InventoryPluginRegister
from rest_framework.authtoken.models import Token

from netdoc_collector.core.ansible_inventory import (
    NetDocAnsibleInventory,
)
from netdoc_collector.core.scanner import NetworkScanner


class TestScanManaged:
    """Managed scan upload data to the backend."""

    @pytest.fixture(autouse=True)
    def setup(self, live_server):
        InventoryPluginRegister.register('NetDocAnsibleInventory', NetDocAnsibleInventory)

        collector_username = 'conftest-collector'
        collector_password = '986629a7ca89202a3ef2ae1dd9d5fb37'

        # Create tenant
        tenant = Tenant.objects.create(name='conftest-tenant')

        # Create collector user
        User = get_user_model()
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
        site = Site.objects.create(name='Conftest Site', is_default=True, tenant=tenant)

        # Create credential
        credential = Credential.objects.create(
            label='Conftest Credential', username='admin', password='admin', tenant=tenant
        )

        # Create and enable collector
        collector = Collector.objects.create(
            name='collector@conftest',
            version='0.0.0',
            is_active=True,
            user=collector_user,
            tenant=tenant,
        )

        self.CLIENT = client
        self.TENANT = tenant
        self.SITE = site
        self.CREDENTIAL = credential
        self.COLLECTOR = collector

    @patch.object(NetworkScanner, '_check_port', return_value=False)
    def test_scan_unreachable_host(self, _mock_check_port):
        scanner = NetworkScanner(
            cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
            cmd_timeout=60,
            concurrency=5,
            credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
            networks=[ipaddress.IPv4Network('10.0.0.1/32')],
            ports=[22],
            report_path=None,
            timeout=0.1,
            client=self.CLIENT,
        )
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)

        assert len(hosts) == 0
        assert scan_completed_hosts == 0
        assert scan_failed_hosts == 0

    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_unsupported(self, _mock_check_port, mock_ssh_detect):
        # Mock result
        mock_ssh_detect.return_value.autodetect.return_value = 'fake_vendor'

        scanner = NetworkScanner(
            cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
            cmd_timeout=60,
            concurrency=5,
            credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
            networks=[ipaddress.IPv4Network('10.0.0.1/32')],
            ports=[22],
            report_path=None,
            timeout=0.1,
            client=self.CLIENT,
        )
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)

        assert len(hosts) == 0
        assert scan_completed_hosts == 0
        assert scan_failed_hosts == 0

    @patch('netdoc_collector.core.scanner.InitNornir')
    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_failed(self, _mock_check_port, mock_ssh_detect, mock_init_nornir):
        # Mock result
        mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'
        fake_nr = MagicMock()
        fake_nr.run.return_value = _fake_discovery_result('10.0.0.1', failed=True)
        mock_init_nornir.return_value = fake_nr

        scanner = NetworkScanner(
            cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
            cmd_timeout=60,
            concurrency=5,
            credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
            networks=[ipaddress.IPv4Network('10.0.0.1/32')],
            ports=[22],
            report_path=None,
            timeout=0.1,
            client=self.CLIENT,
        )
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
        scanner.complete(hosts)

        assert len(hosts) == 1
        assert scan_completed_hosts == 0
        assert scan_failed_hosts == 1

    @patch('netdoc_collector.core.scanner.InitNornir')
    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_discovery(self, _mock_check_port, mock_ssh_detect, mock_init_nornir):
        # Mock result
        mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'
        fake_nr = MagicMock()
        fake_nr.run.return_value = _fake_discovery_result('10.0.0.1', failed=False)
        mock_init_nornir.return_value = fake_nr

        scanner = NetworkScanner(
            cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
            cmd_timeout=60,
            concurrency=5,
            credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
            networks=[ipaddress.IPv4Network('10.0.0.1/32')],
            ports=[22],
            report_path=None,
            timeout=0.1,
            # credentials: list[dict],
            # report_path: Path,
            # claim_token: str | None = None,
            client=self.CLIENT,
            # idempotency_key: str | None = None,
            # job_id: str | None = None,
        )
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
        scanner.complete(hosts)

        assert len(hosts) == 1
        assert scan_completed_hosts == 1
        assert scan_failed_hosts == 0
