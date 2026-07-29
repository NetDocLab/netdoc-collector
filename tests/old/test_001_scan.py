# tests/test_scanner.py
"""Unit tests for NetworkScanner, mocking network I/O, Netmiko and Nornir."""

import ipaddress
from unittest.mock import MagicMock, patch

import pytest
from nornir.core.task import AggregatedResult, MultiResult, Result

from netdoc_collector.core.scanner import NetworkScanner

# scan_workers = num_workers * 10
# scanner = NetworkScanner(
#     cancel_event=cancel_event,
#     cmd_timeout=cmd_timeout,
#     concurrency=scan_workers,
#     credentials=credentials,
#     networks=networks,
#     ports=[22, 23, 80, 443],
#     report_path=report_path,
#     timeout=0.5,
# )
# logger.info('Starting scan with %d workers', scan_workers)
# hosts = scanner.scan()
# scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
# logger.info(
#     'Scan-triggered discovery completed on %d/%d host(s)',
#     scan_completed_hosts,
#     scan_completed_hosts + scan_failed_hosts,
# )
# scanner.complete(hosts, inventory_file=inventory_file)


def _fake_discovery_result(host_name: str, failed: bool = False) -> AggregatedResult:
    """Build a minimal fake AggregatedResult, as if nr.run(discovery_task) had executed."""
    agg = AggregatedResult('discovery_task')
    multi = MultiResult('discovery_task')
    multi.append(
        Result(
            host=MagicMock(name=host_name),
            result=None if failed else {'raw_outputs': {}, 'parsed_outputs': {}},
            failed=failed,
        )
    )
    agg[host_name] = multi
    return agg


@pytest.fixture
def scanner():
    return NetworkScanner(
        cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
        cmd_timeout=60,
        concurrency=5,
        credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
        networks=['192.168.1.0/30'],
        ports=[22],
        report_path=None,
        timeout=0.1,
    )


class TestScan:
    # @patch('netdoc_collector.core.scanner.InitNornir')
    # @patch('netdoc_collector.core.scanner.SSHDetect')
    # @patch.object(NetworkScanner, '_check_port', return_value=True)
    # def test_scan_host_runs_discovery_on_match(
    #     self, _mock_check_port, mock_ssh_detect, mock_init_nornir, scanner
    # ):
    #     # Simulate a successful Netmiko OS autodetect (no real SSH connection made).
    #     mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'

    #     # Simulate what the nornir plugin returns from nr.run(task=discovery_task, ...).
    #     fake_nr = MagicMock()
    #     fake_nr.run.return_value = _fake_discovery_result('10.0.0.1', failed=False)
    #     mock_init_nornir.return_value = fake_nr

    #     result = scanner._scan_host('10.0.0.1')

    #     assert isinstance(result, HostResult)
    #     assert result.netdoc_plugin == 'netmiko:cisco:ios:ssh'
    #     fake_nr.run.assert_called_once()

    # @patch('netdoc_collector.core.scanner.InitNornir')
    # @patch('netdoc_collector.core.scanner.SSHDetect')
    # @patch.object(NetworkScanner, '_check_port', return_value=True)
    # def test_scan_host(
    #     self, _mock_check_port, mock_ssh_detect, mock_init_nornir, scanner, caplog
    # ):
    #     mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'
    #     fake_nr = MagicMock()
    #     fake_nr.run.return_value = _fake_discovery_result('10.0.0.1', failed=True)
    #     mock_init_nornir.return_value = fake_nr

    #     result = scanner._scan_host('10.0.0.1')

    #     assert result is not None  # current behavior, see bug #3 above
    #     assert 'Discovery failed on 10.0.0.1' in caplog.text

    # @patch.object(NetworkScanner, '_check_port', return_value=False)
    # def test_scan_host_returns_none_when_port_closed(self, mock_check_port, scanner):
    #     assert scanner._scan_host('10.0.0.1') is None

    # @patch.object(NetworkScanner, '_check_port', return_value=True) # Ports are closed
    # def test_scan_host_returns_none_when_port_closed(self, _mock_check_port, scanner):
    #     scanner = NetworkScanner(
    #         cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
    #         cmd_timeout=60,
    #         concurrency=5,
    #         credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
    #         networks=[ipaddress.IPv4Network("192.168.1.0/30")],
    #         ports=[22],
    #         report_path=None,
    #         timeout=0.1,
    #     )
    #     hosts = scanner.scan()
    #     scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
    #     assert scan_completed_hosts == 0
    #     assert scan_failed_hosts == 0
    #     # logger.info(
    #     #     'Scan-triggered discovery completed on %d/%d host(s)',
    #     #     scan_completed_hosts,
    #     #     scan_completed_hosts + scan_failed_hosts,
    #     # )
    #     # scanner.complete(hosts, inventory_file=inventory_file)

    # @patch('netdoc_collector.core.scanner.InitNornir')
    # @patch('netdoc_collector.core.scanner.SSHDetect')
    # @patch.object(NetworkScanner, '_check_port', return_value=True)
    # def test_scan_active_host_fail_to_discover(
    #     self, _mock_check_port, mock_ssh_detect, mock_init_nornir, scanner, caplog
    # ):
    #     mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'
    #     fake_nr = MagicMock()
    #     fake_nr.run.return_value = _fake_discovery_result('10.0.0.1', failed=True)
    #     mock_init_nornir.return_value = fake_nr

    #     result = scanner._scan_host('10.0.0.1')

    #     assert result is not None
    #     assert result.discovery_failed is False

    #     print("DAINO", caplog.text, result)
    #     assert 'Discovery failed on 10.0.0.1' in caplog.text

    # OK
    #     @patch.object(NetworkScanner, '_check_port', return_value=False)
    #     def test_scan_unreachable_host(
    #         self, _mock_check_port, scanner
    #     ):
    #         scanner = NetworkScanner(
    #             cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
    #             cmd_timeout=60,
    #             concurrency=5,
    #             credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
    #             networks=[ipaddress.IPv4Network("10.0.0.1/32")],
    #             ports=[22],
    #             report_path=None,
    #             timeout=0.1,
    #         )
    #         hosts = scanner.scan()
    #         scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
    #         assert scan_completed_hosts == 0
    #         assert scan_failed_hosts == 0

    # OK
    # @patch('netdoc_collector.core.scanner.SSHDetect')
    # @patch.object(NetworkScanner, '_check_port', return_value=True)
    # def test_scan_active_host_unsupported(
    #     self, _mock_check_port, mock_ssh_detect, scanner
    # ):
    #     # Mock result
    #     mock_ssh_detect.return_value.autodetect.return_value = 'fake_vendor'

    #     scanner = NetworkScanner(
    #         cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
    #         cmd_timeout=60,
    #         concurrency=5,
    #         credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
    #         networks=[ipaddress.IPv4Network("10.0.0.1/32")],
    #         ports=[22],
    #         report_path=None,
    #         timeout=0.1,
    #     )
    #     hosts = scanner.scan()
    #     scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
    #     assert scan_completed_hosts == 0
    #     assert scan_failed_hosts == 0

    @patch('netdoc_collector.core.scanner.InitNornir')
    @patch('netdoc_collector.core.scanner.SSHDetect')
    @patch.object(NetworkScanner, '_check_port', return_value=True)
    def test_scan_active_host_fail_to_discover(
        self, _mock_check_port, mock_ssh_detect, mock_init_nornir, scanner
    ):
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
        )
        hosts = scanner.scan()
        scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
        print('DAINO', hosts[0].discovery_failed)
        assert scan_completed_hosts == 1
        assert scan_failed_hosts == 1


# OK
#     @patch('netdoc_collector.core.scanner.InitNornir')
#     @patch('netdoc_collector.core.scanner.SSHDetect')
#     @patch.object(NetworkScanner, '_check_port', return_value=True)
#     def test_scan_active_host_discover(
#         self, _mock_check_port, mock_ssh_detect, mock_init_nornir, scanner
#     ):
#         # Mock result
#         mock_ssh_detect.return_value.autodetect.return_value = 'cisco_ios'
#         fake_nr = MagicMock()
#         fake_nr.run.return_value = _fake_discovery_result('10.0.0.1', failed=False)
#         mock_init_nornir.return_value = fake_nr

#         scanner = NetworkScanner(
#             cancel_event=MagicMock(is_set=MagicMock(return_value=False)),
#             cmd_timeout=60,
#             concurrency=5,
#             credentials=[{'label': 'default', 'username': 'admin', 'password': 'admin'}],
#             networks=[ipaddress.IPv4Network("10.0.0.1/32")],
#             ports=[22],
#             report_path=None,
#             timeout=0.1,
#         )
#         hosts = scanner.scan()
#         scan_completed_hosts, scan_failed_hosts = NetworkScanner.summarize_discovery(hosts)
#         assert scan_completed_hosts == 1
#         assert scan_failed_hosts == 0
