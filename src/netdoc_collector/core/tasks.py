"""Nornir discovery tasks and plugin dispatch helpers.

This module runs device discovery for each host in the inventory. In managed
mode it also uploads the collected results and host-specific log records to
NetDoc before returning.
"""

import json
import logging
from pathlib import Path
from threading import Event

from netdoc_sdk.client import NetDocSyncClient
from netdoc_sdk.exceptions import NetDocError
from nornir.core.task import Result, Task

from netdoc_collector.core.utils import collect_task_logs, format_log_record
from netdoc_collector.plugins.dispatcher import get_plugin


def send_collector_heartbeat(
    collector_client: NetDocSyncClient,
    name: str,
    version: str,
    stop_event: Event,
    interval: int = 30,
) -> None:
    """Send periodic collector heartbeats until shutdown is requested.

    Runs in a dedicated background thread until stop_event is set. Any
    communication failure stops the heartbeat and requests shutdown by setting
    the shared stop event.
    """
    while not stop_event.is_set():
        try:
            collector_client.collectors_heartbeat(name=name, version=version)
        except Exception:
            logging.exception('Collector heartbeat failed')
            stop_event.set()
            return
        stop_event.wait(interval)


def mark_job_as_completed(
    collector_client: NetDocSyncClient,
    id: str,
    claim_token: str,
    status: str,
    logs: list[logging.LogRecord] | None = None,
) -> None:
    """Close the current discovery job with the requested final status.

    Used for both the normal end-of-run flow and signal-driven shutdown.

    Args:
        collector_client: NetDoc SDK client instance.
        id: discovery job identifier.
        claim_token: claim token for the current collector.
        status: final status ('completed', 'failed', or 'canceled').
        logs: job-level log records to attach to the completion request.

    Raises:
        ValidationError: propagated so callers can react with a distinct exit
            code when needed.
    """
    if status == 'completed':
        logging.info('Closing discovery job %s as %s', id, status)
    else:
        logging.warning('Closing discovery job %s as %s', id, status)

    collector_client.discovery_jobs_complete(
        id=id,
        claim_token=claim_token,
        data={
            'status': status,
            'logs': [format_log_record(r) for r in (logs or [])],
        },
    )


def discovery_task(
    task: Task,
    report_path: Path,
    client: NetDocSyncClient | None,
    job_id: str | None,
    claim_token: str | None,
    idempotency_key: str | None,
    cancel_event: Event,
    cmd_timeout: int | None = None,
) -> Result:
    """Execute discovery for a single host and push results in managed mode.

    Log records emitted while processing this host are collected and uploaded
    together with the raw and parsed outputs before the task returns.

    Before doing any work, the task checks cancel_event. If another host's
    push response already marked the job as cancelling, this task exits early
    instead of continuing discovery work.

    Args:
        task: Nornir task instance.
        report_path: directory used to store raw reports.
        client: NetDoc SDK client; None in stand-alone mode.
        job_id: discovery job identifier (managed mode only).
        claim_token: claim token for the current collector (managed mode only).
        idempotency_key: job idempotency key (managed mode only).
        cancel_event: shared event set when the backend reports the job as
            cancelling.
        cmd_timeout: optional per-command timeout override.

    Returns:
        Nornir Result object.
    """
    host = task.host
    netdoc_plugin = host.data.get('netdoc_plugin')

    if cancel_event.is_set():
        logging.warning("Skipping host '%s': job is canceling", host.name)
        return Result(
            host=host,
            failed=True,
            exception=RuntimeError('Job canceled before this host started'),
            result=None,
        )

    with collect_task_logs() as task_logs:
        if not netdoc_plugin:
            exc = ValueError(f"Host '{host.name}' is missing 'netdoc_plugin' in host.data")
            logging.error(str(exc))
            result = Result(host=host, failed=True, exception=exc, result=None)
        else:
            plugin = get_plugin(
                host_data=dict(host.data),
                host_name=host.name,
                plugin=netdoc_plugin,
                report_path=report_path,
                cmd_timeout=cmd_timeout,
            )
            try:
                netdoc_output = plugin.collect(task)
                result = Result(host=host, result=netdoc_output)
            except Exception as exc:
                logging.exception('Discovery failed on host %s', host.name)
                result = Result(host=host, failed=True, exception=exc, result=None)

        # Write data locally
        _write_local_data(
            host=host,
            result=result,
            task_logs=task_logs,
            report_path=report_path,
        )

        # Push before the task returns. Concurrency is bounded by
        # num_workers (one push per host, in flight at most once per
        # worker thread), never by the number of commands executed.
        if (
            client is not None
            and job_id is not None
            and claim_token is not None
            and idempotency_key is not None
        ):
            _push_discovered_device(
                client=client,
                job_id=job_id,
                claim_token=claim_token,
                idempotency_key=idempotency_key,
                host=host,
                result=result,
                task_logs=task_logs,
                cancel_event=cancel_event,
            )

    return result


def _write_local_data(
    host,
    result: Result,
    task_logs: list[logging.LogRecord],
    report_path: Path | None,
) -> None:
    """Dump payload locally.

    Args:
        host: Nornir host object.
        result: result already computed for the host's discovery task.
        task_logs: log records captured while processing this host.
        report_path: per-run report directory (output_dir/<timestamp>).
    """
    if not report_path:
        # Write local data only when a report path is available (same as BasePlugin).
        return

    payload = {
        'name': host.name,
        'username': host.data.get('ansible_user'),
        'discovery_address': host.data.get('ansible_host'),
        'discovery_mode': host.data.get('netdoc_plugin'),
        'canonical_device': host.data.get('netdoc_id'),
        'credential': host.data.get('netdoc_credential_id'),
        'raw_payload': None if result.failed else result.result,
        'logs': [format_log_record(r) for r in task_logs],
    }

    # Write metadata
    log_file = host.name
    with open(report_path / Path(f'{log_file}-meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2)


def _push_discovered_device(
    client: NetDocSyncClient,
    job_id: str,
    claim_token: str,
    idempotency_key: str,
    host,
    result: Result,
    task_logs: list[logging.LogRecord],
    cancel_event: Event,
) -> None:
    """Push raw and parsed outputs plus task logs for a single host.

    Failures are logged but do not raise. A push failure must not overwrite the
    result already computed for the host.

    If the backend reports the job status as cancelling, the shared event is
    set so that other in-flight or pending tasks stop promptly.

    Args:
        client: NetDoc SDK client.
        job_id: discovery job identifier.
        claim_token: claim token for the current collector.
        idempotency_key: job idempotency key.
        host: Nornir host object.
        result: result already computed for the host's discovery task.
        task_logs: log records captured while processing this host.
        cancel_event: shared event set when the backend reports that the job is
            being cancelled.
    """
    payload = {
        'raw_payload': None if result.failed else result.result,
        'logs': [format_log_record(r) for r in task_logs],
        'idempotency_key': idempotency_key,
    }
    if host.data.get('netdoc_id'):
        # Discovery an existent device
        payload['canonical_device'] = host.data.get('netdoc_id')
    else:
        # Discovery a new device (scan)
        payload['discovery_mode'] = host.data.get('netdoc_plugin')
        payload['discovery_address'] = host.data.get('ansible_host')
        payload['credential'] = host.data.get('netdoc_credential_id')

    try:
        response = client.discovery_jobs_push_discovered_device(
            id=job_id,
            claim_token=claim_token,
            data=payload,
        )
        logging.info("Push completed for host '%s'", host.name)

        job_status = getattr(response, 'status', None) or response.get('status')
        if job_status == 'cancelling' and not cancel_event.is_set():
            logging.warning('Backend reported job as cancelling — stopping further hosts')
            cancel_event.set()
    except NetDocError as e:
        logging.error(
            "Push failed for host '%s': status=%s detail=%s",
            host.name,
            e.status_code,
            e.detail,
        )
