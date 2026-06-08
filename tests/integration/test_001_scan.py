import os
import pytest
from netdoc_collector.core.scanner import NetworkScanner
from tests.conftest import skip_ios_device_tests


class TestScan:
    @pytest.mark.skipif(skip_ios_device_tests() == True, reason='Skip device related tests')
    async def test_scan_ssh(self, ios_device):
        scanner = NetworkScanner(timeout=5, concurrency=1, **ios_device['scan'])
        hosts = [host async for host in scanner.scan()]
        assert len(hosts) == 1
        host = hosts[0]
        assert host.port == 22
        assert host.netmiko_device_type == 'cisco_ios'
        assert host.netdoc_plugin == 'netmiko:cisco:ios:ssh'
