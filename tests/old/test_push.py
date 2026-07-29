# tests/test_tasks_push.py
"""Tests for the discovery task's push-to-backend logic, mocking the SDK client."""

from unittest.mock import MagicMock

from netdoc_sdk.exceptions import NetDocError

from netdoc_collector.core.tasks import _push_discovered_device


def test_push_discovered_device_success():
    client = MagicMock()
    client.discovery_jobs_push_discovered_device.return_value = MagicMock(status='running')
    host = MagicMock()
    host.name = '10.0.0.1'
    host.data = {'netdoc_id': 'canonical-device-uuid'}

    result = MagicMock(failed=False, result={'raw_outputs': {}})
    cancel_event = MagicMock(is_set=MagicMock(return_value=False))

    _push_discovered_device(
        client=client,
        job_id='job-1',
        claim_token='tok',
        idempotency_key='idem',
        host=host,
        result=result,
        task_logs=[],
        cancel_event=cancel_event,
    )

    client.discovery_jobs_push_discovered_device.assert_called_once()
    call_kwargs = client.discovery_jobs_push_discovered_device.call_args.kwargs
    assert call_kwargs['data']['canonical_device'] == 'canonical-device-uuid'


def test_push_discovered_device_backend_error_is_logged_not_raised():
    client = MagicMock()
    client.discovery_jobs_push_discovered_device.side_effect = NetDocError(
        'Validation failed', status_code=400
    )
    host = MagicMock(name='10.0.0.1', data={'netdoc_id': None})
    result = MagicMock(failed=False, result={})
    cancel_event = MagicMock(is_set=MagicMock(return_value=False))

    # Must not raise: current behavior swallows NetDocError and only logs it
    # (this is exactly bug #2 above — you can use this test to reproduce it).
    _push_discovered_device(
        client=client,
        job_id='job-1',
        claim_token='tok',
        idempotency_key='idem',
        host=host,
        result=result,
        task_logs=[],
        cancel_event=cancel_event,
    )


def test_push_discovered_device_sets_cancel_event_when_backend_reports_cancelling():
    client = MagicMock()
    client.discovery_jobs_push_discovered_device.return_value = MagicMock(status='cancelling')
    host = MagicMock(name='10.0.0.1', data={'netdoc_id': 'uuid'})
    result = MagicMock(failed=False, result={})
    cancel_event = MagicMock(is_set=MagicMock(return_value=False))

    _push_discovered_device(
        client=client,
        job_id='job-1',
        claim_token='tok',
        idempotency_key='idem',
        host=host,
        result=result,
        task_logs=[],
        cancel_event=cancel_event,
    )

    cancel_event.set.assert_called_once()
