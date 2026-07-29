"""Unit tests for the collector's main entrypoint (netdoc_collector.main)."""

import json
import logging
import signal as signal_module
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from netdoc_sdk.exceptions import AuthenticationError, ValidationError

from netdoc_collector import main as main_module
from netdoc_collector.core.utils import MainLogCollector

# ─────────────────────────────────────────────
#  Test doubles
# ─────────────────────────────────────────────


class ImmediateThread:
    """Fake Thread that never actually runs its target in the background.

    Used to avoid real background threads (heartbeat) during tests.
    `start()` is a no-op by default.
    """

    def __init__(self, target=None, kwargs=None, daemon=None, name=None):
        self._target = target
        self._kwargs = kwargs or {}
        self.name = name

    def start(self) -> None:
        pass

    def join(self, timeout=None) -> None:
        pass


class ImmediatelyFailingThread(ImmediateThread):
    """Fake Thread simulating a heartbeat thread that fails on first run."""

    def start(self) -> None:
        self._kwargs['stop_event'].set()


def make_results(statuses: list[bool]) -> dict:
    """Build a fake Nornir AggregatedResult-like dict.

    Args:
        statuses: list of `failed` booleans, one per host.

    Returns:
        dict mapping fake host names to fake per-host results.
    """
    return {f'host-{i}': SimpleNamespace(failed=failed) for i, failed in enumerate(statuses)}


def run_main(monkeypatch, argv):
    """Run main() with the given CLI arguments (argv[0] excluded)."""
    monkeypatch.setattr('sys.argv', ['netdoc-collector', *argv])
    return main_module.main()


# ─────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_root_logger():
    """Snapshot and restore root logger state around every test.

    main() adds handlers to the root logger (debug console handler,
    MainLogCollector) and, in some paths, never removes them. Without this
    isolation, handlers would accumulate across tests and cause flaky
    cross-test interference.
    """
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


@pytest.fixture
def patched(monkeypatch):
    """Patch all external collaborators of main() with harmless defaults.

    Returns a namespace of the mocks so individual tests can override
    return values / side effects as needed.
    """
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.collectors_heartbeat.return_value = None

    mock_nr = MagicMock()
    mock_nr.inventory.hosts = {'host-0': object()}
    mock_nr.run.return_value = make_results([False])

    mock_init_nornir = MagicMock(return_value=mock_nr)
    mock_scanner_cls = MagicMock()
    mock_scanner_instance = MagicMock()
    mock_scanner_cls.return_value = mock_scanner_instance
    mock_scanner_instance.scan.return_value = []

    mock_log_collector_cls = MagicMock()
    mock_log_collector = MagicMock(spec=MainLogCollector)
    mock_log_collector.level = logging.NOTSET
    mock_log_collector.drain.return_value = []
    mock_log_collector_cls.return_value = mock_log_collector

    mock_mark_job_as_completed = MagicMock()

    monkeypatch.setattr(main_module, 'NetDocSyncClient', mock_client_cls)
    monkeypatch.setattr(main_module, 'InitNornir', mock_init_nornir)
    monkeypatch.setattr(main_module, 'InventoryPluginRegister', MagicMock())
    monkeypatch.setattr(main_module, 'NetworkScanner', mock_scanner_cls)
    monkeypatch.setattr(main_module, 'Thread', ImmediateThread)
    monkeypatch.setattr(main_module, 'MainLogCollector', mock_log_collector_cls)
    monkeypatch.setattr(main_module, 'cleanup_old_snapshots', MagicMock())
    monkeypatch.setattr(main_module, 'mark_job_as_completed', mock_mark_job_as_completed)
    monkeypatch.setattr(signal_module, 'signal', MagicMock())

    # Avoid environment-dependent calls (package metadata, real hostname/user).
    monkeypatch.setattr(main_module, 'version', MagicMock(return_value='0.0.0-test'))
    monkeypatch.setattr(main_module.getpass, 'getuser', lambda: 'testuser')
    monkeypatch.setattr(main_module.socket, 'getfqdn', lambda: 'collector.example.com')

    return SimpleNamespace(
        client_cls=mock_client_cls,
        client=mock_client,
        nr=mock_nr,
        init_nornir=mock_init_nornir,
        scanner_cls=mock_scanner_cls,
        scanner=mock_scanner_instance,
        log_collector=mock_log_collector,
        mark_job_as_completed=mock_mark_job_as_completed,
    )


@pytest.fixture
def valid_inventory_file(tmp_path):
    """Write a minimal valid Ansible-style inventory JSON file."""
    inventory = {
        '_meta': {'hostvars': {'device-1': {'ansible_host': '10.0.0.1'}}},
        'all': {'hosts': ['device-1']},
    }
    path = tmp_path / 'inventory.json'
    path.write_text(json.dumps(inventory))
    return path


# ─────────────────────────────────────────────
#  Mode selection / early exits
# ─────────────────────────────────────────────


class TestModeSelection:
    def test_no_backend_and_no_inventory_returns_4(self, monkeypatch, patched):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={'inventory': ''}))
        assert run_main(monkeypatch, []) == 4

    def test_invalid_inventory_json_returns_3(self, monkeypatch, patched, tmp_path):
        bad_file = tmp_path / 'bad.json'
        bad_file.write_text('{not valid json')
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        assert run_main(monkeypatch, ['--inventory', str(bad_file)]) == 3


# ─────────────────────────────────────────────
#  Stand-alone mode: scan
# ─────────────────────────────────────────────


class TestScanMode:
    def test_no_credentials_returns_6(self, monkeypatch, patched):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        assert run_main(monkeypatch, ['--scan']) == 6

    def test_invalid_network_returns_5(self, monkeypatch, patched):
        monkeypatch.setattr(
            main_module,
            'load_config',
            MagicMock(return_value={'credentials': [{'username': 'u', 'password': 'p'}]}),
        )
        # /33 is an out-of-range IPv4 prefix length -> ipaddress.NetmaskValueError,
        # the specific exception the code catches.
        assert run_main(monkeypatch, ['--scan', '--network', '10.0.0.0/33']) == 5

    def test_success_saves_inventory_and_returns_0(self, monkeypatch, patched):
        monkeypatch.setattr(
            main_module,
            'load_config',
            MagicMock(return_value={'credentials': [{'username': 'u', 'password': 'p'}]}),
        )
        patched.scanner.scan.return_value = []

        assert run_main(monkeypatch, ['--scan', '--network', '10.0.0.0/30']) == 0

        patched.scanner_cls.assert_called_once()
        patched.scanner.save_inventory.assert_called_once()


# ─────────────────────────────────────────────
#  Stand-alone mode: discovery
# ─────────────────────────────────────────────


class TestStandAloneDiscovery:
    def test_success_returns_0(self, monkeypatch, patched, valid_inventory_file):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.nr.run.return_value = make_results([False])

        code = run_main(monkeypatch, ['--inventory', str(valid_inventory_file)])

        assert code == 0
        patched.mark_job_as_completed.assert_not_called()

    def test_failed_hosts_returns_2(self, monkeypatch, patched, valid_inventory_file):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.nr.run.return_value = make_results([True])

        assert run_main(monkeypatch, ['--inventory', str(valid_inventory_file)]) == 2


# ─────────────────────────────────────────────
#  Managed mode
# ─────────────────────────────────────────────

MANAGED_ARGS = ['--url', 'http://backend.example.com', '--token', 'tok123']


class TestManagedMode:
    def test_initial_heartbeat_auth_failure_returns_11(self, monkeypatch, patched):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.client.collectors_heartbeat.side_effect = AuthenticationError('bad token')

        assert run_main(monkeypatch, MANAGED_ARGS) == 11

    def test_claim_job_validation_error_returns_7(self, monkeypatch, patched):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.client.discovery_jobs_claim.side_effect = ValidationError('bad request')

        assert run_main(monkeypatch, MANAGED_ARGS) == 7

    def test_no_job_to_claim_returns_0(self, monkeypatch, patched):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.client.discovery_jobs_claim.return_value = None

        assert run_main(monkeypatch, MANAGED_ARGS) == 0
        patched.nr.run.assert_not_called()

    def test_heartbeat_failure_during_setup_returns_9(self, monkeypatch, patched):
        """If the heartbeat thread fails before Nornir starts, abort with 9."""
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        monkeypatch.setattr(main_module, 'Thread', ImmediatelyFailingThread)
        patched.client.discovery_jobs_claim.return_value = SimpleNamespace(
            id='job-1',
            idempotency_key='idem-1',
            claim_token='claim-1',
            inventory={'all': {'hosts': ['h1']}},
        )

        assert run_main(monkeypatch, MANAGED_ARGS) == 9
        patched.nr.run.assert_not_called()

    def test_all_hosts_succeed_closes_job_as_completed(self, monkeypatch, patched):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.client.discovery_jobs_claim.return_value = SimpleNamespace(
            id='job-1',
            idempotency_key='idem-1',
            claim_token='claim-1',
            inventory={'all': {'hosts': ['h1', 'h2']}},
        )
        patched.nr.run.return_value = make_results([False, False])

        code = run_main(monkeypatch, MANAGED_ARGS)

        assert code == 0
        patched.mark_job_as_completed.assert_called_once()
        _, kwargs = patched.mark_job_as_completed.call_args
        assert kwargs['id'] == 'job-1'
        assert kwargs['claim_token'] == 'claim-1'
        assert kwargs['status'] == 'completed'

    def test_all_hosts_fail_closes_job_as_failed_returns_2(self, monkeypatch, patched):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.client.discovery_jobs_claim.return_value = SimpleNamespace(
            id='job-1',
            idempotency_key='idem-1',
            claim_token='claim-1',
            inventory={'all': {'hosts': ['h1', 'h2']}},
        )
        patched.nr.run.return_value = make_results([True, True])

        code = run_main(monkeypatch, MANAGED_ARGS)

        assert code == 2
        _, kwargs = patched.mark_job_as_completed.call_args
        assert kwargs['status'] == 'failed'

    def test_cancel_event_closes_job_as_canceled(self, monkeypatch, patched):
        """If a task push reports the job as canceling, the job closes as canceled."""
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.client.discovery_jobs_claim.return_value = SimpleNamespace(
            id='job-1',
            idempotency_key='idem-1',
            claim_token='claim-1',
            inventory={'all': {'hosts': ['h1']}},
        )

        def fake_run(**kwargs):
            # Simulate a worker task noticing the job is canceling mid-run.
            kwargs['cancel_event'].set()
            return make_results([False])

        patched.nr.run.side_effect = fake_run

        code = run_main(monkeypatch, MANAGED_ARGS)

        assert code == 0  # no failed hosts, independent of cancellation
        _, kwargs = patched.mark_job_as_completed.call_args
        assert kwargs['status'] == 'canceled'

    def test_close_job_validation_error_returns_10(self, monkeypatch, patched):
        monkeypatch.setattr(main_module, 'load_config', MagicMock(return_value={}))
        patched.client.discovery_jobs_claim.return_value = SimpleNamespace(
            id='job-1',
            idempotency_key='idem-1',
            claim_token='claim-1',
            inventory={'all': {'hosts': ['h1']}},
        )
        patched.mark_job_as_completed.side_effect = ValidationError('could not close')

        assert run_main(monkeypatch, MANAGED_ARGS) == 10


# ─────────────────────────────────────────────
#  entrypoint()
# ─────────────────────────────────────────────


class TestEntrypoint:
    def test_returns_main_exit_code(self, monkeypatch):
        monkeypatch.setattr(main_module, 'main', MagicMock(return_value=42))
        assert main_module.entrypoint() == 42
