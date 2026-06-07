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
    collector_client: NetDocClient, name: str, version: str, interval=30
):
    """Send periodic collector heartbeat to NetDoc server.

    Sends a heartbeat signal at regular intervals (default 30 seconds) to indicate
    the collector is alive and operational. Runs as an infinite background task.
    On any failure, logs the error and exits the entire program with status code 1.

    Args:
        collector_client (NetDocClient): Client instance for communicating with NetDoc server.
        name (str): Name identifier for this collector instance.
        version (str): Version of the collector software.
        interval (int): Heartbeat interval in seconds. Defaults to 30.

    Raises:
        SystemExit: Exits the program (status 1) if heartbeat fails.
    """
    while True:
        try:
            await collector_client.collector_heartbeat(name=name, version=version)
        except Exception as exc:
            logging.error(exc)
            sys.exit(1)
        await asyncio.sleep(interval)


async def send_job_heartbeat(
    collector_client: NetDocClient, id: str, claim_token: str, interval=30
):
    """Send periodic job heartbeat to NetDoc server.

    Sends a heartbeat signal at regular intervals (default 30 seconds) to indicate
    the discovery job is still running and active. Runs as an infinite background task.
    On any failure, logs the error and exits the entire program with status code 1.

    Args:
        collector_client (NetDocClient): Client instance for communicating with NetDoc server.
        id (str): Unique identifier for the discovery job.
        claim_token (str): Authentication token to claim ownership of the job.
        interval (int): Heartbeat interval in seconds. Defaults to 30.

    Raises:
        SystemExit: Exits the program (status 1) if heartbeat fails.
    """
    while True:
        try:
            await collector_client.discoveryjob_heartbeat(id=id, claim_token=claim_token)
        except Exception as exc:
            logging.error(exc)
            sys.exit(1)
        await asyncio.sleep(interval)


async def mark_job_as_failed(
    collector_client: NetDocClient, id: str, claim_token: str, interval=30
):
    """Mark the current discovery job as failed and exit.

    This helper attempts to complete the current discovery job with a failed
    status when the collector is interrupted or when an unrecoverable error
    occurs. If the completion call fails, the process exits with code 1.

    Args:
        collector_client (NetDocClient): Client instance for communicating with NetDoc server.
        id (str): Unique identifier for the discovery job.
        claim_token (str): Authentication token to claim ownership of the job.
        interval (int): Unused placeholder for compatibility with heartbeat helpers.

    Raises:
        SystemExit: Exits the program with status 1 if the failure callback cannot complete the job.
    """
    logging.error('Collector interrupted; marking discovery job as failed.')
    try:
        await collector_client.discoveryjob_complete(
            id=id, claim_token=claim_token, status='failed'
        )
    except Exception as exc:
        logging.error(exc)
        sys.exit(1)


def discovery_task(
    task: Task,
    report_path: Path,
    cmd_timeout=None,
) -> Result:
    """Execute the NetDoc plugin discovery workflow for one host.

    Args:
        task (Task): Nornir task object representing the host execution context.
        report_path (Path): directory where raw output reports are stored.
        cmd_timeout (int | None): override command timeout for this host.

    Returns:
        Result: Nornir Result object containing plugin output or failure.
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
