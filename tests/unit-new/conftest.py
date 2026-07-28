from unittest.mock import MagicMock

from nornir.core.task import AggregatedResult, MultiResult, Result


def _fake_discovery_result(host_name: str, failed: bool = False) -> AggregatedResult:
    """Build a minimal fake AggregatedResult, as if nr.run(discovery_task) had executed."""
    agg = AggregatedResult('discovery_task')
    multi = MultiResult('discovery_task')
    multi.append(
        Result(
            host=MagicMock(name=host_name),
            result=None if failed else {'raw_outputs': {}, 'parsed_outputs': {}},
            failed=failed,
        )
    )
    agg[host_name] = multi
    return agg
