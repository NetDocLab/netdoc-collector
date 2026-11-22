"""Shared Cisco VRF discovery helpers."""

from collections.abc import Iterable, Mapping


def discovered_vrf_names(rows: Iterable[Mapping[str, object]]) -> list[str]:
    """Keep each discovered VRF in source order and add the default when absent."""
    names: dict[str, None] = {}
    for row in rows:
        name = str(row.get('name', '')).strip()
        if name:
            names[name] = None
    return list(names) if 'default' in names else ['default', *names]
