# Usage

This page provides common usage examples for the netdoc-collector CLI.

## Stand-alone mode

Read a local Ansible-style JSON inventory and write the results to ./output:

```bash
netdoc-collector -i inventory.json -c config.yaml
```

Override the output directory and worker count:

```bash
netdoc-collector -i inventory.json -o ./output -w 10
```

## Managed mode

Claim jobs from the NetDoc backend and push the collected payloads back to it:

```bash
export NETDOC_TOKEN="<your-api-token>"
netdoc-collector --url https://netdoc.example.com --token "$NETDOC_TOKEN"
```

You can also provide the token and URL directly as CLI flags:

```bash
netdoc-collector --url https://netdoc.example.com --token mytoken --workers 8
```

## L2/L3 command coverage

The Cisco IOS, IOS-XE and NX-OS plugins retain native command output for
the backend to interpret. Command selection and positive platform evidence
determine which scoped observations can be submitted. Empty or unavailable
output does not establish that a feature is disabled. For release-specific
validation records, see the [NetDoc L2/L3 implementation tracker](https://github.com/NetDocLab/netdoc/issues/215).

Managed discovery integration tests use the matching backend checkout and
its PostgreSQL test settings. Tenant setup creates the root Site used by
new Devices.

## Files

- config.yaml: primary configuration for collector behavior
- secrets.yaml: SSH credentials used by the scanner; protect it with strict file permissions
- inventory.json: Ansible-style inventory with _meta.hostvars

Keep secrets out of version control and secure secrets.yaml with restrictive permissions.
