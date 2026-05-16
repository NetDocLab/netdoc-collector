"""
Result aggregator and YAML writer.

Collects the per-host results produced by discovery_task and writes
a single YAML file with the following structure:

  metadata:
    generated_at: "2024-01-15T10:30:00"
    total_hosts: 2
    failed_hosts: 0

  hosts:
    router1:
      vendor: cisco
      platform: ios
      site: rome
      interfaces:
        GigabitEthernet0/0:
          status: up
          ...
    router2:
      ...
"""

from pathlib import Path
import os
import json
import logging
from datetime import datetime, timezone
from typing import Any

import yaml
from nornir.core.task import AggregatedResult

logger = logging.getLogger(__name__)


def aggregate_and_write(results: AggregatedResult, output_path: str) -> dict[str, Any]:
    """
    Aggregate Nornir results and write to a YAML file.

    Args:
        results:     AggregatedResult from nr.run()
        output_path: filesystem path for the output YAML

    Returns:
        The aggregated dict (also written to disk).
    """

    device_data = []
    errors = []
    failed_host_num = 0

    # hosts_data: dict[str, Any] = {}
    # failed: list[str] = []

    for host_name, multi_result in results.items():
        if multi_result.failed:
            error = f'Discovery failed on {host_name}: '
            error += str(multi_result.exception or "unknown error")
            errors.append(error)
            failed_host_num += 1
            continue

        # The last Result in MultiResult is the return value of discovery_task itself
        task_result = multi_result[0].result
        if task_result is not None:
            device_data.append(
                {
                    "name": host_name,
                    "result": task_result['netdoc_output'],
                }
            )
        else:
            errors.append(f"Task on {host_name} returned no data")

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_hosts": len(results),
            "successful_hosts": len(results) - failed_host_num,
            "errors": errors,
        },
        "devices": device_data,
    }

    # Write to disk
    if output_path:
        output_path.mkdir(exist_ok=True, parents=True)
        with open(output_path / Path(f'netdoc-report.json'), 'w', encoding='utf-8') as fh:
            json.dump(output, fh, indent=2)
        return

    return output
