"""
Nornir task: discovery_task

This is the function passed to nr.run(). It runs on every host in parallel.

Steps per host:
  1. Determine vendor and platform from host data/inventory
  2. Instantiate the correct plugin via the dispatcher
  3. Open an SSH connection (via netmiko)
  4. Execute each command returned by plugin.commands()
  5. Pass raw outputs to plugin.parse()
  6. Return plugin.to_yaml_dict() as the task result
"""

from pathlib import Path
from nornir.core.task import Task, Result
from netdoc_discovery.plugins.dispatcher import get_plugin


def discovery_task(task: Task, report_path: Path) -> Result:
    host = task.host
    netdoc_plugin = host.data.get('netdoc_plugin')

    if not netdoc_plugin:
        return Result(
            host=host,
            result=None,
            failed=True,
            exception=ValueError(
                f"Host '{host.name}' is missing 'netdoc_plugin' in host.data"
            ),
        )

    plugin = get_plugin(
        plugin=netdoc_plugin,
        host_name=host.name,
        host_data=dict(host.data),
        report_path=report_path,
    )

    netdoc_output = plugin.collect(task)

    return Result(host=host, result=netdoc_output)
