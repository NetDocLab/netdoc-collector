"""Collect IOS IS-IS circuits for the configured process tag in each VRF."""

import re


def ios_isis_processes(config: str) -> dict[str, list[str]]:
    processes: dict[str, list[str]] = {}
    active_tag = None
    contexts: set[str] = set()
    for line in [*config.splitlines(), 'end']:
        if not line.strip() or line.strip() == '!':
            continue
        if not line[0].isspace():
            if active_tag and len(contexts) <= 1:
                context = next(iter(contexts), 'default')
                processes.setdefault(context, []).append(active_tag)
            process = re.fullmatch(r'router isis ([\w.:-]+)', line.strip(), re.ASCII)
            active_tag = process[1] if process else None
            contexts = set()
        elif active_tag and (match := re.fullmatch(r'vrf ([\w.:-]+)', line.strip(), re.ASCII)):
            contexts.add(match[1])
    return processes


def ios_isis_commands(config: str, vrf: str) -> list[str]:
    return [
        f'show clns {tag} is-neighbors detail'
        for tag in dict.fromkeys(ios_isis_processes(config).get(vrf, []))
    ]
