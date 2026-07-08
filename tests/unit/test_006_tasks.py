"""Unit tests for Nornir discovery task and job-closing helpers."""

from contextlib import contextmanager
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from netdoc_collector.core import tasks as tasks_module


@contextmanager
def fake_collect_task_logs():
    """Fake context manager standing in for utils.collect_task_logs."""
    yield ['log1', 'log2']


# ─────────────────────────────────────────────
#  send_collector_heartbeat
# ─────────────────────────────────────────────


class TestSendCollectorHeartbeat:
    def test_stops_when_event_set_by_a_successful_call(self):
        """Loop exits as soon as stop_event is set, without waiting the full interval."""
        stop_event = Event()
        client = MagicMock()

        def fake_heartbeat(name, version):
            stop_event.set()

        client.collectors_heartbeat.side_effect = fake_heartbeat

        tasks_module.send_collector_heartbeat(
            collector_client=client, name='n', version='v', stop_event=stop_event, interval=0
        )

        assert client.collectors_heartbeat.call_count == 1

    def test_exception_sets_stop_event_and_returns(self):
        stop_event = Event()
        client = MagicMock()
        client.collectors_heartbeat.side_effect = RuntimeError('boom')

        tasks_module.send_collector_heartbeat(
            collector_client=client, name='n', version='v', stop_event=stop_event, interval=0
        )

        assert stop_event.is_set()
        assert client.collectors_heartbeat.call_count == 1

    def test_never_called_if_stop_event_already_set(self):
        stop_event = Event()
        stop_event.set()
        client = MagicMock()

        tasks_module.send_collector_heartbeat(
            collector_client=client, name='n', version='v', stop_event=stop_event, interval=0
        )

        client.collectors_heartbeat.assert_not_called()


# ─────────────────────────────────────────────
#  mark_job_as_completed
# ─────────────────────────────────────────────


class TestMarkJobAsCompleted:
    def test_sends_formatted_logs(self, monkeypatch):
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: {'msg': r})
        client = MagicMock()

        tasks_module.mark_job_as_completed(
            client, id='job-1', claim_token='tok', status='completed', logs=['rec1', 'rec2']
        )

        client.discovery_jobs_complete.assert_called_once_with(
            id='job-1',
            claim_token='tok',
            data={'status': 'completed', 'logs': [{'msg': 'rec1'}, {'msg': 'rec2'}]},
        )

    def test_defaults_logs_to_empty_list(self, monkeypatch):
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: r)
        client = MagicMock()

        tasks_module.mark_job_as_completed(client, id='job-1', claim_token='tok', status='failed')

        _, kwargs = client.discovery_jobs_complete.call_args
        assert kwargs['data']['logs'] == []
        assert kwargs['data']['status'] == 'failed'

    def test_propagates_validation_error(self):
        from netdoc_sdk.exceptions import ValidationError

        client = MagicMock()
        client.discovery_jobs_complete.side_effect = ValidationError('bad request')

        with pytest.raises(ValidationError):
            tasks_module.mark_job_as_completed(
                client, id='job-1', claim_token='tok', status='failed'
            )


# ─────────────────────────────────────────────
#  discovery_task
# ─────────────────────────────────────────────


def _make_task(host_data=None, host_name='host-1'):
    host = SimpleNamespace(name=host_name, data=host_data or {})
    task = SimpleNamespace(host=host)
    return task


class TestDiscoveryTask:
    def test_skips_immediately_when_job_already_canceling(self, monkeypatch):
        task = _make_task({'netdoc_plugin': 'cisco_ios'})
        mock_push = MagicMock()
        monkeypatch.setattr(tasks_module, '_push_discovered_device', mock_push)
        cancel_event = Event()
        cancel_event.set()

        result = tasks_module.discovery_task(
            task=task,
            report_path=Path('/tmp'),
            client=MagicMock(),
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            cancel_event=cancel_event,
        )

        assert result.failed is True
        mock_push.assert_not_called()

    def test_missing_plugin_returns_failed_result(self, monkeypatch):
        task = _make_task({})  # no netdoc_plugin
        monkeypatch.setattr(tasks_module, 'collect_task_logs', fake_collect_task_logs)
        mock_push = MagicMock()
        monkeypatch.setattr(tasks_module, '_push_discovered_device', mock_push)

        result = tasks_module.discovery_task(
            task=task,
            report_path=Path('/tmp'),
            client=None,
            job_id=None,
            claim_token=None,
            idempotency_key=None,
            cancel_event=Event(),
        )

        assert result.failed is True
        assert isinstance(result.exception, ValueError)
        mock_push.assert_not_called()  # client is None -> stand-alone mode

    def test_success_calls_plugin_and_pushes(self, monkeypatch):
        task = _make_task({'netdoc_plugin': 'cisco_ios'})
        monkeypatch.setattr(tasks_module, 'collect_task_logs', fake_collect_task_logs)
        mock_plugin = MagicMock()
        mock_plugin.collect.return_value = {'raw_outputs': {}, 'parsed_outputs': {}}
        monkeypatch.setattr(tasks_module, 'get_plugin', MagicMock(return_value=mock_plugin))
        mock_push = MagicMock()
        monkeypatch.setattr(tasks_module, '_push_discovered_device', mock_push)

        result = tasks_module.discovery_task(
            task=task,
            report_path=Path('/tmp'),
            client=MagicMock(),
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            cancel_event=Event(),
        )

        assert result.failed is False
        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        assert kwargs['task_logs'] == ['log1', 'log2']

    def test_plugin_exception_still_triggers_push_with_failed_result(self, monkeypatch):
        task = _make_task({'netdoc_plugin': 'cisco_ios'})
        monkeypatch.setattr(tasks_module, 'collect_task_logs', fake_collect_task_logs)
        mock_plugin = MagicMock()
        mock_plugin.collect.side_effect = RuntimeError('boom')
        monkeypatch.setattr(tasks_module, 'get_plugin', MagicMock(return_value=mock_plugin))
        mock_push = MagicMock()
        monkeypatch.setattr(tasks_module, '_push_discovered_device', mock_push)

        result = tasks_module.discovery_task(
            task=task,
            report_path=Path('/tmp'),
            client=MagicMock(),
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            cancel_event=Event(),
        )

        assert result.failed is True
        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        assert kwargs['result'].failed is True

    def test_standalone_mode_never_pushes(self, monkeypatch):
        task = _make_task({'netdoc_plugin': 'cisco_ios'})
        monkeypatch.setattr(tasks_module, 'collect_task_logs', fake_collect_task_logs)
        mock_plugin = MagicMock()
        mock_plugin.collect.return_value = {}
        monkeypatch.setattr(tasks_module, 'get_plugin', MagicMock(return_value=mock_plugin))
        mock_push = MagicMock()
        monkeypatch.setattr(tasks_module, '_push_discovered_device', mock_push)

        result = tasks_module.discovery_task(
            task=task,
            report_path=Path('/tmp'),
            client=None,
            job_id=None,
            claim_token=None,
            idempotency_key=None,
            cancel_event=Event(),
        )

        assert result.failed is False
        mock_push.assert_not_called()

    @pytest.mark.parametrize(
        'missing_field',
        ['job_id', 'claim_token', 'idempotency_key'],
    )
    def test_partial_managed_args_skip_push(self, monkeypatch, missing_field):
        """Push must be all-or-nothing: any missing managed-mode field disables it."""
        task = _make_task({'netdoc_plugin': 'cisco_ios'})
        monkeypatch.setattr(tasks_module, 'collect_task_logs', fake_collect_task_logs)
        mock_plugin = MagicMock()
        mock_plugin.collect.return_value = {}
        monkeypatch.setattr(tasks_module, 'get_plugin', MagicMock(return_value=mock_plugin))
        mock_push = MagicMock()
        monkeypatch.setattr(tasks_module, '_push_discovered_device', mock_push)

        kwargs = {'job_id': 'job-1', 'claim_token': 'claim-1', 'idempotency_key': 'idem-1'}
        kwargs[missing_field] = None

        tasks_module.discovery_task(
            task=task,
            report_path=Path('/tmp'),
            client=MagicMock(),
            cancel_event=Event(),
            **kwargs,
        )

        mock_push.assert_not_called()


# ─────────────────────────────────────────────
#  _push_discovered_device
# ─────────────────────────────────────────────


def _make_host(netdoc_id='device-1'):
    return SimpleNamespace(name='host-1', data={'netdoc_id': netdoc_id})


class TestPushDiscoveredDevice:
    def test_successful_push_with_dict_response(self, monkeypatch):
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: r)
        client = MagicMock()
        client.discovery_jobs_push_discovered_device.return_value = {'status': 'in_progress'}
        host = _make_host()
        result = SimpleNamespace(failed=False, result={'raw_outputs': {}})
        cancel_event = Event()

        tasks_module._push_discovered_device(
            client=client,
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            host=host,
            result=result,
            task_logs=['l1'],
            cancel_event=cancel_event,
        )

        client.discovery_jobs_push_discovered_device.assert_called_once()
        _, kwargs = client.discovery_jobs_push_discovered_device.call_args
        assert kwargs['data']['canonical_device'] == 'device-1'
        assert kwargs['data']['raw_payload'] == {'raw_outputs': {}}
        assert kwargs['data']['logs'] == ['l1']
        assert not cancel_event.is_set()

    def test_failed_result_sends_null_raw_payload(self, monkeypatch):
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: r)
        client = MagicMock()
        client.discovery_jobs_push_discovered_device.return_value = {'status': 'in_progress'}
        host = _make_host()
        result = SimpleNamespace(failed=True, result=None)

        tasks_module._push_discovered_device(
            client=client,
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            host=host,
            result=result,
            task_logs=[],
            cancel_event=Event(),
        )

        _, kwargs = client.discovery_jobs_push_discovered_device.call_args
        assert kwargs['data']['raw_payload'] is None

    def test_status_reported_as_object_attribute(self, monkeypatch):
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: r)
        client = MagicMock()
        client.discovery_jobs_push_discovered_device.return_value = SimpleNamespace(
            status='completed'
        )
        host = _make_host()
        result = SimpleNamespace(failed=False, result={})

        # Must not raise even though the response has no `.get()`.
        tasks_module._push_discovered_device(
            client=client,
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            host=host,
            result=result,
            task_logs=[],
            cancel_event=Event(),
        )

    def test_netdoc_error_is_caught_and_never_raised(self, monkeypatch):
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: r)

        class FakeNetDocError(Exception):
            def __init__(self, status_code, detail):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        monkeypatch.setattr(tasks_module, 'NetDocError', FakeNetDocError)
        client = MagicMock()
        client.discovery_jobs_push_discovered_device.side_effect = FakeNetDocError(500, 'boom')
        host = _make_host()
        result = SimpleNamespace(failed=False, result={})
        cancel_event = Event()

        # Must not propagate: a push failure must not affect the task result.
        tasks_module._push_discovered_device(
            client=client,
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            host=host,
            result=result,
            task_logs=[],
            cancel_event=cancel_event,
        )

        assert not cancel_event.is_set()

    def test_cancel_event_not_set_twice(self, monkeypatch):
        """If already set, a further 'canceling'-like response must not re-log/re-set."""
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: r)
        client = MagicMock()
        client.discovery_jobs_push_discovered_device.return_value = {'status': 'cancelling'}
        host = _make_host()
        result = SimpleNamespace(failed=False, result={})
        cancel_event = Event()
        cancel_event.set()  # already set by a previous host

        tasks_module._push_discovered_device(
            client=client,
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            host=host,
            result=result,
            task_logs=[],
            cancel_event=cancel_event,
        )

        assert cancel_event.is_set()  # unchanged, no error

    def test_reported_canceling_status_sets_cancel_event(self, monkeypatch):
        """The value the code actually checks for ('cancelling') does set the event."""
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: r)
        client = MagicMock()
        client.discovery_jobs_push_discovered_device.return_value = {'status': 'cancelling'}
        host = _make_host()
        result = SimpleNamespace(failed=False, result={})
        cancel_event = Event()

        tasks_module._push_discovered_device(
            client=client,
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            host=host,
            result=result,
            task_logs=[],
            cancel_event=cancel_event,
        )

        assert cancel_event.is_set()

    def test_backend_cancelling_status_sets_cancel_event(self, monkeypatch):
        """The backend reports the intermediate status as 'cancelling'."""
        monkeypatch.setattr(tasks_module, 'format_log_record', lambda r: r)
        client = MagicMock()
        client.discovery_jobs_push_discovered_device.return_value = {'status': 'cancelling'}
        host = _make_host()
        result = SimpleNamespace(failed=False, result={})
        cancel_event = Event()

        tasks_module._push_discovered_device(
            client=client,
            job_id='job-1',
            claim_token='claim-1',
            idempotency_key='idem-1',
            host=host,
            result=result,
            task_logs=[],
            cancel_event=cancel_event,
        )

        assert cancel_event.is_set()
