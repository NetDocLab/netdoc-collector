"""Unit tests for NetworkScanner (stand alone)."""

import ipaddress
import json
from unittest.mock import MagicMock, patch

from netdoc_collector.core.scanner import NetworkScanner


class TestScanStandalone:
    """Stand alone scan stops after platform detection."""

    @patch.object(NetworkScanner, '_check_port', return_value=False)
    def test_scan_unreachable_host(self, _mock_check_port, tmp_path):
        inventory_file = tmp_path / 'inventory.json'
        scanner = NetworkScanner(
            cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
            cmd_timeout=60,
            concurrency=5,
            credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
            networks=[ipaddress.IPv4Network('10.0.0.1/32')],
            ports=[22],
            report_path=tmp_path,
            timeout=0.1,
        )
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
        scanner.complete(hosts, inventory_file=inventory_file)

        assert len(hosts) == 0
        assert scan_completed_hosts == 0
        assert scan_failed_hosts == 0
        assert inventory_file.exists()
        data = json.loads(inventory_file.read_text())
        assert data == {'_meta': {'hostvars': {}}, 'all': {'hosts': []}}

    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_unsupported(self, _mock_check_port, mock_ssh_detect, tmp_path):
        # Mock result
        mock_ssh_detect.return_value.autodetect.return_value = 'fake_vendor'

        inventory_file = tmp_path / 'inventory.json'
        scanner = NetworkScanner(
            cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
            cmd_timeout=60,
            concurrency=5,
            credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
            networks=[ipaddress.IPv4Network('10.0.0.1/32')],
            ports=[22],
            report_path=tmp_path,
            timeout=0.1,
        )
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
        scanner.complete(hosts, inventory_file=inventory_file)

        assert len(hosts) == 0
        assert scan_completed_hosts == 0
        assert scan_failed_hosts == 0
        assert inventory_file.exists()
        data = json.loads(inventory_file.read_text())
        assert data == {'_meta': {'hostvars': {}}, 'all': {'hosts': []}}

    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_supported(self, _mock_check_port, mock_ssh_detect, tmp_path):
        # Mock result
        mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'

        inventory_file = tmp_path / 'inventory.json'
        scanner = NetworkScanner(
            cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
            cmd_timeout=60,
            concurrency=5,
            credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
            networks=[ipaddress.IPv4Network('10.0.0.1/32')],
            ports=[22],
            report_path=tmp_path,
            timeout=0.1,
        )
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
        scanner.complete(hosts, inventory_file=inventory_file)

        assert len(hosts) == 1
        assert scan_completed_hosts == 1
        assert scan_failed_hosts == 0
        assert inventory_file.exists()
        data = json.loads(inventory_file.read_text())
        assert data == {
            '_meta': {
                'hostvars': {
                    '10.0.0.1': {
                        'ansible_host': '10.0.0.1',
                        'ansible_password': 'admin',
                        'ansible_port': 22,
                        'ansible_user': 'admin',
                        'netdoc_credential_id': None,
                        'netdoc_plugin': 'netmiko:cisco:ios:ssh',
                        'netmiko_device_type': 'cisco_ios',
                    }
                }
            },
            'all': {'hosts': ['10.0.0.1']},
        }
