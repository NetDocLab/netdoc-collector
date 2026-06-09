"""Nornir discovery task and plugin dispatch helpers.

This module implements the task executed by Nornir for every host in the
inventory. It resolves the configured NetDoc plugin, executes device
collection, and returns structured results.
"""

import asyncio
import logging
import sys
from pathlib import Path

from netdoc_sdk.client import NetDocClient
from nornir.core.task import Result, Task

from netdoc_collector.plugins.dispatcher import get_plugin


async def send_collector_heartbeat(
    collector_client: NetDocClient,
    name: str,
    version: str,
    stop_event: asyncio.Event,
    interval: int = 30,
) -> None:
    """Send periodic collector heartbeat to NetDoc server.

    Sends a heartbeat signal at regular intervals to indicate the collector is
    alive and operational. Runs until `stop_event` is set. On any failure, logs
    the error and signals the stop event so the main loop can exit cleanly.

    Args:
        collector_client: Client instance for communicating with NetDoc server.
        name: Name identifier for this collector instance.
        version: Version of the collector software.
        stop_event: Event used to signal the main loop to stop.
        interval: Heartbeat interval in seconds. Defaults to 30.
    """
    while not stop_event.is_set():
        try:
            await collector_client.collector_heartbeat(name=name, version=version)
        except Exception as exc:
            logging.error('Collector heartbeat failed: %s', exc)
            stop_event.set()
            return
        await asyncio.sleep(interval)


async def send_job_heartbeat(
    collector_client: NetDocClient,
    id: str,
    claim_token: str,
    stop_event: asyncio.Event,
    interval: int = 30,
) -> None:
    """Send periodic job heartbeat to NetDoc server.

    Sends a heartbeat signal at regular intervals to indicate the discovery job
    is still running. Runs until `stop_event` is set. On any failure, logs the
    error and signals the stop event so the main loop can exit cleanly.

    Args:
        collector_client: Client instance for communicating with NetDoc server.
        id: Unique identifier for the discovery job.
        claim_token: Authentication token to claim ownership of the job.
        stop_event: Event used to signal the main loop to stop.
        interval: Heartbeat interval in seconds. Defaults to 30.
    """
    while not stop_event.is_set():
        try:
            await collector_client.discoveryjob_heartbeat(id=id, claim_token=claim_token)
        except Exception as exc:
            logging.error('Job heartbeat failed: %s', exc)
            stop_event.set()
            return
        await asyncio.sleep(interval)


async def mark_job_as_failed(
    collector_client: NetDocClient,
    id: str,
    claim_token: str,
) -> None:
    """Mark the current discovery job as failed.

    Attempts to complete the current discovery job with a failed status when
    the collector is interrupted or an unrecoverable error occurs.

    Args:
        collector_client: Client instance for communicating with NetDoc server.
        id: Unique identifier for the discovery job.
        claim_token: Authentication token to claim ownership of the job.
    """
    logging.error('Collector interrupted; marking discovery job as failed.')
    try:
        await collector_client.discoveryjob_complete(
            id=id, claim_token=claim_token, status='failed'
        )
    except Exception as exc:
        logging.error('Failed to mark job as failed: %s', exc)
        sys.exit(1)


def discovery_task(
    task: Task,
    report_path: Path,
    cmd_timeout=None,
) -> Result:
    """Execute the NetDoc plugin discovery workflow for one host.

    Args:
        task: Nornir task object representing the host execution context.
        report_path: Directory where raw output reports are stored.
        cmd_timeout: Override command timeout for this host.

    Returns:
        Nornir Result object containing plugin output or failure details.
    """
    host = task.host
    netdoc_plugin = host.data.get('netdoc_plugin')

    if not netdoc_plugin:
        return Result(
            exception=ValueError(f"Host '{host.name}' is missing 'netdoc_plugin' in host.data"),
            failed=True,
            host=host,
            result=None,
        )

    plugin = get_plugin(
        host_data=dict(host.data),
        host_name=host.name,
        plugin=netdoc_plugin,
        report_path=report_path,
        cmd_timeout=cmd_timeout,
    )

    netdoc_output = plugin.collect(task)

    return Result(host=host, result=netdoc_output)
