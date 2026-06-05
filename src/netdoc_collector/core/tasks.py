"""Nornir discovery task and plugin dispatch helpers.

This module implements the task executed by Nornir for every host in the
inventory. It resolves the configured NetDoc plugin, executes device
collection, and returns structured results.
"""

from pathlib import Path

from nornir.core.task import Result, Task

from netdoc_collector.plugins.dispatcher import get_plugin


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
