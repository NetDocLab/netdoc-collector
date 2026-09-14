import ipaddress
from unittest.mock import MagicMock, patch

import pytest
from netmiko.exceptions import ReadTimeout
from nornir.core.plugins.inventory import InventoryPluginRegister

from netdoc_collector.core.ansible_inventory import NetDocAnsibleInventory
from netdoc_collector.core.scanner import HostResult, NetworkScanner


class TestScan:
    @pytest.mark.parametrize(
        ('image_lines', 'expected_type'),
        [
            pytest.param(
                '  kickstart image file is: /bootflash/aci-n9000-dk9.14.2.1i.bin\n'
                '  system image file is: /bootflash/auto-s',
                'cisco_aci',
                id='aci-leaf',
            ),
            pytest.param(
                '  kickstart image file is: /bootflash/aci-n9000-dk9.16.1.3f-cs_64.bin',
                'cisco_aci',
                id='aci-spine',
            ),
            pytest.param(
                '\tNXOS image file name is: bootflash:///ACI-N9000-dk9.16.1.3f.bin\r\n',
                'cisco_aci',
                id='case-and-whitespace',
            ),
            pytest.param(
                '  system image file is: aci-n9000-dk9.14.2.1i.bin',
                'cisco_aci',
                id='bare-image-name',
            ),
            pytest.param(
                '  NXOS image file is: bootflash:///nxos.7.0.3.I7.3.bin',
                'cisco_nxos',
                id='standalone-nxos',
            ),
            pytest.param(
                '  NXOS image file is: bootflash:///n9000-dk9.6.1.2.I3.4.bin',
                'cisco_nxos',
                id='standalone-n9000',
            ),
            pytest.param(
                '  kickstart image file is: bootflash:///n7000-s2-kickstart.6.2.16.bin\n'
                '  system image file is: bootflash:///n7000-s2-dk9.6.2.16.bin',
                'cisco_nxos',
                id='legacy-standalone-kickstart',
            ),
            pytest.param(
                '  Device name: aci-n9000-leaf\n'
                '  NXOS image file is: bootflash:///nxos.7.0.3.I7.3.bin',
                'cisco_nxos',
                id='aci-in-hostname-only',
            ),
            pytest.param('', 'cisco_nxos', id='missing-version-output'),
        ],
    )
    def test_probe_distinguishes_nxos_and_aci(self, scanner, image_lines, expected_type):
        with patch('netdoc_collector.core.scanner.SSHDetect') as detect:
            guesser = detect.return_value
            guesser.autodetect.return_value = 'cisco_nxos'
            guesser._results_cache = (
                {'show version': 'Cisco Nexus Operating System (NX-OS) Software\n' + image_lines}
                if image_lines
                else {}
            )

            device_type, credential = scanner._probe_host_via_netmiko('10.0.0.1')

        assert device_type == expected_type
        assert credential is scanner.credentials[0]
        detect.assert_called_once()
        guesser.autodetect.assert_called_once_with()
        assert guesser.connection.mock_calls == []

    def test_scan_skips_aci_before_collection(self, scanner, caplog):
        scanner.client = MagicMock()
        with (
            patch.object(NetworkScanner, '_check_port', return_value=True),
            patch('netdoc_collector.core.scanner.SSHDetect') as detect,
            patch('netdoc_collector.core.scanner.InitNornir') as init_nornir,
            caplog.at_level('INFO', logger='scanner'),
        ):
            guesser = detect.return_value
            guesser.autodetect.return_value = 'cisco_nxos'
            guesser._results_cache = {
                'show version': 'kickstart image file is: /bootflash/aci-n9000-dk9.14.2.1i.bin'
            }

            hosts = scanner.scan()

        assert hosts == []
        assert 'unsupported device type cisco_aci' in caplog.text
        init_nornir.assert_not_called()

    def test_scan_aggregates_results_and_survives_exceptions(self, scanner):
        scanner.networks = [ipaddress.IPv4Network('10.0.0.0/30')]  # 2 usable hosts

        def fake_scan_host(ip):
            if ip.endswith('.1'):
                raise RuntimeError('simulated netmiko crash')
            return HostResult(ip=ip, netdoc_plugin='netmiko:cisco:ios:ssh')

        with patch.object(NetworkScanner, '_scan_host', side_effect=fake_scan_host):
            results = scanner.scan()

        assert len(results) == 1  # the exception must not abort the whole scan

    @pytest.mark.parametrize(
        'error', [ReadTimeout('Pattern not detected'), OSError('Socket is closed')]
    )
    def test_scan_counts_interrupted_collection_as_failed(self, scanner, monkeypatch, error):
        """Replay a command failure after one successful command through the real plugin."""
        InventoryPluginRegister.register('NetDocAnsibleInventory', NetDocAnsibleInventory)
        scanner.client = MagicMock()
        scanner.client.discovery_jobs_push_discovered_device.return_value = {'status': 'running'}
        scanner.job_id = 'job'
        scanner.claim_token = 'claim'
        scanner.idempotency_key = 'key'
        connection = MagicMock(secret='')
        connection.send_command.side_effect = ['first command output', error]
        monkeypatch.setattr('nornir.core.inventory.Host.get_connection', lambda *_args: connection)
        monkeypatch.setattr(NetworkScanner, '_check_port', lambda *_args: True)
        monkeypatch.setattr(
            NetworkScanner,
            '_probe_host_via_netmiko',
            lambda *_args: ('cisco_nxos', scanner.credentials[0]),
        )

        hosts = scanner.scan()

        assert connection.send_command.call_count == 2
        assert len(hosts) == 1
        assert hosts[0].discovery_failed is True
        assert scanner.summarize_discovery(hosts) == (0, 1)

    @pytest.mark.parametrize('failed', [False, True])
    def test_scan_closes_each_hosts_connections(self, scanner, monkeypatch, failed):
        """A finished per-host Nornir must release sessions even when discovery failed."""
        InventoryPluginRegister.register('NetDocAnsibleInventory', NetDocAnsibleInventory)
        scanner.client = MagicMock()
        connection = MagicMock()

        def collect(task):
            task.host.connections['netmiko'] = connection
            if failed:
                raise OSError('Socket is closed')
            return {'raw_outputs': {}, 'parsed_outputs': {}}

        monkeypatch.setattr(
            'netdoc_collector.core.tasks.get_plugin',
            lambda **_kwargs: MagicMock(collect=collect),
        )
        monkeypatch.setattr(NetworkScanner, '_check_port', lambda *_args: True)
        monkeypatch.setattr(
            NetworkScanner,
            '_probe_host_via_netmiko',
            lambda *_args: ('cisco_nxos', scanner.credentials[0]),
        )

        hosts = scanner.scan()

        assert len(hosts) == 1
        assert hosts[0].discovery_failed is failed
        connection.close.assert_called_once_with()
