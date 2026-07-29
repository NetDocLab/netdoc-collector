# tests/test_main_managed.py
"""End-to-end test of main() in managed mode with the backend client fully mocked."""

from unittest.mock import MagicMock, patch


@patch('netdoc_collector.main.NetDocSyncClient')
@patch('netdoc_collector.main.InitNornir')
def test_managed_mode_claims_job_runs_discovery_and_closes_job(
    mock_init_nornir, mock_client_cls, monkeypatch
):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    fake_job = MagicMock(
        id='job-1',
        idempotency_key='idem-1',
        claim_token='token-1',
        inventory={'_meta': {'hostvars': {}}, 'all': {'hosts': []}},
        credentials=[],
        network_ranges=[],
        known_ip_addresses=[],
    )
    mock_client.discovery_jobs_claim.return_value = fake_job

    fake_nr = MagicMock()
    fake_nr.inventory.hosts = {}
    fake_nr.run.return_value = {}  # AggregatedResult vuoto: 0 host, nessun fallimento
    mock_init_nornir.return_value = fake_nr

    monkeypatch.setenv('NETDOC_TOKEN', 'fake-token')
    monkeypatch.setattr('sys.argv', ['netdoc-collector', '-u', 'http://fake-backend'])

    from netdoc_collector.main import main

    exit_code = main()

    mock_client.collectors_heartbeat.assert_called_once()
    mock_client.discovery_jobs_claim.assert_called_once()
    mock_client.discovery_jobs_complete.assert_called_once()
    assert exit_code == 0
