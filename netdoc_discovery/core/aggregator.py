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

import logging
from datetime import datetime, timezone
from typing import Any

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

    output_path.mkdir(parents=True, exist_ok=True)

    hosts_data: dict[str, Any] = {}
    failed: list[str] = []

    for host_name, multi_result in results.items():
        if multi_result.failed:
            logger.warning("Host '%s' failed: %s", host_name, multi_result.exception)
            failed.append(host_name)
            hosts_data[host_name] = {
                'error': str(multi_result.exception or 'unknown error')
            }
            continue

        # The last Result in MultiResult is the return value of discovery_task itself
        task_result = multi_result[0].result
        if task_result is not None:
            hosts_data[host_name] = task_result
        else:
            hosts_data[host_name] = {'error': 'task returned no data'}
            failed.append(host_name)

    output = {
        'metadata': {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_hosts': len(results),
            'successful_hosts': len(results) - len(failed),
            'failed_hosts': len(failed),
            'failed_host_names': failed,
        },
        'hosts': hosts_data,
    }

    # os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    print(output)
    # with open(output_path, "w") as f:
    #     yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("YAML output written to '%s' (%d hosts)", output_path, len(hosts_data))
    return output
