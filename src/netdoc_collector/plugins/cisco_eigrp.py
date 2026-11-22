"""Plan scoped native EIGRP probes from acquired Cisco configuration."""

import re

_TOKEN = r'[a-zA-Z0-9_.:-]+'
_ROUTER = re.compile(rf'router eigrp ({_TOKEN})$')
_VRF = re.compile(rf'vrf ({_TOKEN})$')
_AF = re.compile(
    rf'address-family (ipv[46])(?: unicast)?(?: vrf ({_TOKEN}))?(?: autonomous-system (\d+))?$'
)


def _process_lines(config):
    process = None
    for line in config.splitlines():
        statement = line.strip()
        if not statement or statement.startswith('!'):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            match = _ROUTER.fullmatch(statement)
            process = match[1] if match else None
        if process is not None:
            yield process, indent, statement


def ios_eigrp_commands(config, vrf):
    """Request named-mode tables by their configured family, VRF and AS."""
    commands: dict[str, None] = {}
    for _, indent, statement in _process_lines(config):
        af = _AF.fullmatch(statement) if indent else None
        if af and (af[2] or 'default') == vrf and af[3] and 1 <= int(af[3]) <= 65535:
            scope = '' if vrf == 'default' else f' vrf {vrf}'
            for table in ('neighbors', 'interfaces'):
                commands[f'show eigrp address-family {af[1]}{scope} {af[3]} {table} detail'] = None
    return list(commands)


def eigrp_configured_vrfs(config, *, nxos=False):
    """Find named scopes even when the general show VRF parser is unavailable."""
    names: dict[str, None] = {}
    for _, indent, statement in _process_lines(config):
        match = (_VRF if nxos else _AF).fullmatch(statement) if indent else None
        if match and (name := match[1 if nxos else 2]):
            names[name] = None
    return list(names)


def nxos_eigrp_commands(config, vrf):
    """Request each NX-OS process using its tag and actual configured scope."""
    selectors: dict[tuple[str, str], None] = {}
    scope, vrf_indent = 'default', None
    for process, indent, statement in _process_lines(config):
        if not indent or (vrf_indent is not None and indent <= vrf_indent):
            scope, vrf_indent = 'default', None
        if match := _VRF.fullmatch(statement):
            scope, vrf_indent = match[1], indent
        if scope != vrf:
            continue
        if not indent or _VRF.fullmatch(statement):
            selectors[(process, 'ip')] = None
        elif (af := _AF.fullmatch(statement)) and af[1] == 'ipv6':
            selectors[(process, 'ipv6')] = None
    suffix = '' if vrf == 'default' else f' vrf {vrf}'
    return [
        f'show {family} eigrp {process} {table}{suffix}'
        for process, family in selectors
        for table in ('neighbors detail', 'interfaces brief')
    ]
