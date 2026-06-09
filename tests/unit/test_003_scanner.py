"""Unit tests for the async network scanner module."""

import asyncio
import json
from ipaddress import IPv4Network
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from netdoc_collector.core.scanner import HostResult, NetworkScanner

# ─────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def credentials():
    return [
        {'label': 'admin', 'username': 'admin', 'password': 'secret'},
        {'label': 'readonly', 'username': 'ro', 'password': 'pass'},
    ]


@pytest.fixture
def scanner(credentials):
    return NetworkScanner(
        ports=[22, 80],
        timeout=1.0,
        concurrency=10,
        credentials=credentials,
        networks=[IPv4Network('192.168.1.0/30')],
    )


# ─────────────────────────────────────────────
#  HostResult
# ─────────────────────────────────────────────


class TestHostResult:
    def test_defaults(self):
        host = HostResult(ip='10.0.0.1')
        assert host.ip == '10.0.0.1'
        assert host.port is None
        assert host.netmiko_device_type is None
        assert host.netdoc_plugin is None
        assert host.credential == {}

    def test_full_construction(self):
        host = HostResult(
            ip='10.0.0.1',
            port=22,
            netmiko_device_type='cisco_ios',
            netdoc_plugin='netmiko:cisco:ios:ssh',
            credential={'username': 'u', 'password': 'p'},
        )
        assert host.port == 22
        assert host.netmiko_device_type == 'cisco_ios'
        assert host.netdoc_plugin == 'netmiko:cisco:ios:ssh'


# ─────────────────────────────────────────────
#  _check_port
# ─────────────────────────────────────────────


class TestCheckPort:
    @pytest.mark.asyncio
    async def test_open_port_returns_true(self, scanner):
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        with patch(
            'asyncio.open_connection', new=AsyncMock(return_value=(MagicMock(), mock_writer))
        ):
            result = await scanner._check_port('192.168.1.1', 22)
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_refused_returns_false(self, scanner):
        with patch('asyncio.open_connection', side_effect=ConnectionRefusedError):
            result = await scanner._check_port('192.168.1.1', 22)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self, scanner):
        with patch('asyncio.open_connection', side_effect=TimeoutError):
            result = await scanner._check_port('192.168.1.1', 22)
        assert result is False

    @pytest.mark.asyncio
    async def test_os_error_returns_false(self, scanner):
        with patch('asyncio.open_connection', side_effect=OSError):
            result = await scanner._check_port('192.168.1.1', 22)
        assert result is False

    @pytest.mark.asyncio
    async def test_writer_close_exception_is_suppressed(self, scanner):
        """Exceptions during writer.wait_closed() must not propagate."""
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock(side_effect=RuntimeError('boom'))
        with patch(
            'asyncio.open_connection', new=AsyncMock(return_value=(MagicMock(), mock_writer))
        ):
            result = await scanner._check_port('192.168.1.1', 22)
        assert result is True


# ─────────────────────────────────────────────
#  _probe_host_via_netmiko
# ─────────────────────────────────────────────


class TestProbeHostViaNetmiko:
    def _make_guesser(self, device_type):
        g = MagicMock()
        g.autodetect.return_value = device_type
        return g

    def test_returns_device_type_and_credential(self, scanner):
        with patch('scanner.SSHDetect', return_value=self._make_guesser('cisco_ios')):
            device_type, cred = scanner._probe_host_via_netmiko('10.0.0.1')
        assert device_type == 'cisco_ios'
        assert cred == scanner.credentials[0]

    def test_skips_credential_without_username(self, credentials):
        creds = [{'label': 'empty'}, {'label': 'ok', 'username': 'u', 'password': 'p'}]
        s = NetworkScanner(ports=[22], timeout=1, concurrency=5, credentials=creds, networks=[])
        with patch('scanner.SSHDetect', return_value=self._make_guesser('linux')) as mock_ssh:
            device_type, _cred = s._probe_host_via_netmiko('10.0.0.1')
        # SSHDetect should only be called once (second credential)
        assert mock_ssh.call_count == 1
        assert device_type == 'linux'

    def test_auth_failure_tries_next_credential(self, scanner):
        from netmiko.exceptions import NetmikoAuthenticationException

        with patch(
            'scanner.SSHDetect',
            side_effect=[
                NetmikoAuthenticationException('bad creds'),
                self._make_guesser('aruba_oscx'),
            ],
        ):
            device_type, cred = scanner._probe_host_via_netmiko('10.0.0.1')
        assert device_type == 'aruba_oscx'
        assert cred == scanner.credentials[1]

    def test_all_credentials_fail_returns_none(self, scanner):
        from netmiko.exceptions import NetmikoAuthenticationException

        with patch('scanner.SSHDetect', side_effect=NetmikoAuthenticationException('fail')):
            device_type, cred = scanner._probe_host_via_netmiko('10.0.0.1')
        assert device_type is None
        assert cred is None

    def test_autodetect_returns_none(self, scanner):
        with patch('scanner.SSHDetect', return_value=self._make_guesser(None)):
            device_type, _cred = scanner._probe_host_via_netmiko('10.0.0.1')
        # Loop continues, next credential also returns None → final result is None
        assert device_type is None


# ─────────────────────────────────────────────
#  _scan_host  - plugin mapping
# ─────────────────────────────────────────────

PLUGIN_CASES = [
    ('allied_telesis_awplus', 'allied_telesis_awplus', 'netmiko:allied_telesis:awplus:ssh'),
    ('aruba_oscx', 'aruba_oscx', 'netmiko:aruba:aoscx:ssh'),
    ('cisco_ios', 'cisco_ios', 'netmiko:cisco:ios:ssh'),
    ('cisco_xe', 'cisco_ios', 'netmiko:cisco:ios:ssh'),  # normalised
    ('cisco_nxos', 'cisco_nxos', 'netmiko:cisco:nxos:ssh'),
    ('cisco_xr', 'cisco_xr', 'netmiko:cisco_xr:ssh'),
    ('hp_comware', 'hp_comware', 'netmiko:hp:comware:ssh'),
    ('hp_procurve', 'hp_procurve', 'netmiko:hp:procurve:ssh'),
    ('huawei_vrp', 'huawei_vrp', 'netmiko:huawei:vrp:ssh'),
    ('linux', 'linux', 'netmiko:linux::ssh'),
]


class TestScanHostPluginMapping:
    @pytest.mark.asyncio
    @pytest.mark.parametrize('raw_type,expected_device_type,expected_plugin', PLUGIN_CASES)
    async def test_plugin_mapping(self, scanner, raw_type, expected_device_type, expected_plugin):
        semaphore = asyncio.Semaphore(1)
        cred = {'username': 'admin', 'password': 'secret', 'label': 'admin'}

        with (
            patch.object(scanner, '_check_port', new=AsyncMock(return_value=True)),
            patch.object(scanner, '_probe_host_via_netmiko', return_value=(raw_type, cred)),
        ):
            result = await scanner._scan_host('10.0.0.1', semaphore)

        assert result is not None
        assert result.netmiko_device_type == expected_device_type
        assert result.netdoc_plugin == expected_plugin
        assert result.port == 22

    @pytest.mark.asyncio
    async def test_unknown_device_type_returns_none(self, scanner):
        semaphore = asyncio.Semaphore(1)
        cred = {'username': 'admin', 'password': 'secret', 'label': 'admin'}

        with (
            patch.object(scanner, '_check_port', new=AsyncMock(return_value=True)),
            patch.object(scanner, '_probe_host_via_netmiko', return_value=('unknown_os', cred)),
        ):
            result = await scanner._scan_host('10.0.0.1', semaphore)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_open_ports_returns_none(self, scanner):
        semaphore = asyncio.Semaphore(1)
        with patch.object(scanner, '_check_port', new=AsyncMock(return_value=False)):
            result = await scanner._scan_host('10.0.0.1', semaphore)
        assert result is None

    @pytest.mark.asyncio
    async def test_port_22_not_open_skips_netmiko(self, scanner):
        """If port 22 is closed but another port is open, netmiko must not be called."""
        semaphore = asyncio.Semaphore(1)

        async def port_open(ip, port):
            return port == 80  # only HTTP is open

        with (
            patch.object(scanner, '_check_port', side_effect=port_open),
            patch.object(scanner, '_probe_host_via_netmiko') as mock_probe,
        ):
            result = await scanner._scan_host('10.0.0.1', semaphore)

        mock_probe.assert_not_called()
        assert result is None


# ─────────────────────────────────────────────
#  _iter_hosts
# ─────────────────────────────────────────────


class TestIterHosts:
    @pytest.mark.asyncio
    async def test_yields_host_addresses(self, scanner):
        network = IPv4Network('10.0.0.4/30')
        hosts = []
        async for ip in scanner._iter_hosts(network):
            hosts.append(ip)
        # /30 has 2 usable hosts: .5 and .6
        assert hosts == ['10.0.0.5', '10.0.0.6']

    @pytest.mark.asyncio
    async def test_single_host_network(self, scanner):
        network = IPv4Network('10.0.0.1/32')
        hosts = []
        async for ip in scanner._iter_hosts(network):
            hosts.append(ip)
        assert hosts == ['10.0.0.1']


# ─────────────────────────────────────────────
#  save_inventory
# ─────────────────────────────────────────────


class TestSaveInventory:
    def test_creates_valid_ansible_json(self, tmp_path):
        hosts = [
            HostResult(
                ip='10.0.0.1',
                port=22,
                netmiko_device_type='cisco_ios',
                netdoc_plugin='netmiko:cisco:ios:ssh',
                credential={'username': 'admin', 'password': 'secret'},
            )
        ]
        output = tmp_path / 'inventory.json'
        NetworkScanner.save_inventory(hosts, str(output))

        data = json.loads(output.read_text())
        assert '10.0.0.1' in data['all']['hosts']
        hostvars = data['_meta']['hostvars']['10.0.0.1']
        assert hostvars['ansible_host'] == '10.0.0.1'
        assert hostvars['ansible_user'] == 'admin'
        assert hostvars['ansible_password'] == 'secret'
        assert hostvars['ansible_port'] == 22
        assert hostvars['netdoc_plugin'] == 'netmiko:cisco:ios:ssh'
        assert hostvars['netmiko_device_type'] == 'cisco_ios'

    def test_empty_host_list(self, tmp_path):
        output = tmp_path / 'empty.json'
        NetworkScanner.save_inventory([], str(output))
        data = json.loads(output.read_text())
        assert data['all']['hosts'] == []
        assert data['_meta']['hostvars'] == {}

    def test_multiple_hosts_all_present(self, tmp_path):
        hosts = [
            HostResult(ip=f'10.0.0.{i}', port=22, credential={'username': 'u', 'password': 'p'})
            for i in range(1, 4)
        ]
        output = tmp_path / 'multi.json'
        NetworkScanner.save_inventory(hosts, str(output))
        data = json.loads(output.read_text())
        assert len(data['all']['hosts']) == 3

    def test_output_is_sorted_json(self, tmp_path):
        """Keys in the JSON output must be sorted (sort_keys=True)."""
        hosts = [HostResult(ip='1.2.3.4', port=22, credential={'username': 'u', 'password': 'p'})]
        output = tmp_path / 'sorted.json'
        NetworkScanner.save_inventory(hosts, str(output))
        raw = output.read_text()
        # Re-serialise without sort_keys and compare: if they match, keys were sorted
        data = json.loads(raw)
        assert raw == json.dumps(data, indent=4, sort_keys=True)


# ─────────────────────────────────────────────
#  scan (integration-style, no real network)
# ─────────────────────────────────────────────


class TestScan:
    @pytest.mark.asyncio
    async def test_yields_results_for_active_hosts(self, scanner):
        cred = {'username': 'admin', 'password': 'secret', 'label': 'admin'}
        good_host = HostResult(
            ip='192.168.1.1',
            port=22,
            netmiko_device_type='cisco_ios',
            netdoc_plugin='netmiko:cisco:ios:ssh',
            credential=cred,
        )

        async def fake_scan_network(network):
            yield good_host

        with patch.object(scanner, '_scan_network', side_effect=fake_scan_network):
            results = [h async for h in scanner.scan()]

        assert len(results) == 1
        assert results[0].ip == '192.168.1.1'

    @pytest.mark.asyncio
    async def test_iterates_all_configured_networks(self):
        networks = [IPv4Network('10.0.0.0/30'), IPv4Network('10.0.1.0/30')]
        s = NetworkScanner(ports=[22], timeout=1, concurrency=5, credentials=[], networks=networks)

        seen_networks = []

        async def fake_scan_network(network):
            seen_networks.append(network)
            return
            yield  # make it an async generator

        with patch.object(s, '_scan_network', side_effect=fake_scan_network):
            _ = [h async for h in s.scan()]

        assert seen_networks == networks
