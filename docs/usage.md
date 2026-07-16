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

## Files

- config.yaml: primary configuration for collector behavior
- secrets.yaml: SSH credentials used by the scanner; protect it with strict file permissions
- inventory.json: Ansible-style inventory with _meta.hostvars

Keep secrets out of version control and secure secrets.yaml with restrictive permissions.
