"""Nornir discovery task and plugin dispatch helpers.

This module implements the task executed by Nornir for every host in the
inventory. It resolves the configured NetDoc plugin, executes device
collection, and — in managed mode — pushes the collected data and the
host's own log records to the backend before the task returns.
"""

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
    """Send periodic collector heartbeat.

    Runs in a dedicated background thread until ``stop_event`` is set.
    Any communication failure stops the heartbeat and requests shutdown
    by setting the shared stop event.
    """
    while not stop_event.is_set():
        try:
            collector_client.collectors_heartbeat(name=name, version=version)
        except Exception:
            logging.exception('Collector heartbeat failed')
            stop_event.set()
            return
        stop_event.wait(interval)


def mark_job_as_failed(collector_client: NetDocSyncClient, id: str, claim_token: str) -> None:
    """Mark the current discovery job as failed."""
    logging.error('Collector interrupted; marking discovery job as failed.')
    try:
        collector_client.discovery_jobs_complete(
            id=id, claim_token=claim_token, data={'status': 'failed'}
        )
    except Exception:
        logging.exception('Failed to mark job as failed')


def discovery_task(
    task: Task,
    report_path: Path,
    client: NetDocSyncClient | None,
    job_id: str | None,
    claim_token: str | None,
    idempotency_key: str | None,
    cmd_timeout: int | None = None,
) -> Result:
    """Execute discovery for a single host and, in managed mode, push its results.

    Log records emitted while processing this host (on this worker thread)
    are collected via ``collect_task_logs`` and pushed to the backend
    together with the collected raw/parsed outputs, in a single request,
    right before the task returns.

    Args:
        task: Nornir task.
        report_path: Directory where raw reports are stored.
        client: NetDoc SDK client; ``None`` in stand-alone mode (no push).
        job_id: Discovery job identifier (managed mode only).
        claim_token: Claim token for the current collector (managed mode only).
        idempotency_key: Job idempotency key (managed mode only).
        cmd_timeout: Optional command timeout override.

    Returns:
        Nornir Result object.
    """
    host = task.host
    netdoc_plugin = host.data.get('netdoc_plugin')

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

        # Push before the task returns. Concurrency is bounded by
        # num_workers (one push per host, in flight at most once per
        # worker thread), never by the number of commands executed.
        if client is not None:
            _push_discovered_device(
                client=client,
                job_id=job_id,
                claim_token=claim_token,
                idempotency_key=idempotency_key,
                host=host,
                result=result,
                task_logs=task_logs,
            )

    return result


def _push_discovered_device(
    client: NetDocSyncClient,
    job_id: str,
    claim_token: str,
    idempotency_key: str,
    host,
    result: Result,
    task_logs: list[logging.LogRecord],
) -> None:
    """Push raw/parsed outputs and collected logs for a single host.

    Failures are logged but never raised: a push failure must not affect
    the Nornir task result already computed for this host.

    Args:
        client: NetDoc SDK client.
        job_id: Discovery job identifier.
        claim_token: Claim token for the current collector.
        idempotency_key: Job idempotency key.
        host: Nornir host object.
        result: Result already computed for this host's discovery task.
        task_logs: Log records captured while processing this host.
    """
    try:
        client.discovery_jobs_push_discovered_device(
            id=job_id,
            claim_token=claim_token,
            data={
                'canonical_device': host.data.get('netdoc_id'),
                'idempotency_key': idempotency_key,
                'raw_payload': None if result.failed else result.result,
                'logs': [format_log_record(r) for r in task_logs],
            },
        )
        logging.info("Push completed for host '%s'", host.name)
    except NetDocError as e:
        logging.error(
            "Push failed for host '%s': status=%s detail=%s",
            host.name,
            e.status_code,
            e.detail,
        )
