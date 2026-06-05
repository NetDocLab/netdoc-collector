# Usage

This page shows common usage examples for the `netdoc-collector` CLI.

## Stand-alone mode

Read a local Ansible JSON inventory and write outputs to `./output`:

```bash
netdoc-collector -i inventory.json -c config.yaml
```

Override output directory and workers:

```bash
netdoc-collector -i inventory.json -o ./output -w 10
```

## Managed mode

Claim jobs from the NetDoc backend and push raw payloads back:

```bash
export NETDOC_TOKEN="<your-api-token>"
netdoc-collector --url https://netdoc.example.com --token $NETDOC_TOKEN
```

Or pass token and URL via CLI flags:

```bash
netdoc-collector --url https://netdoc.example.com --token mytoken --workers 8
```

## Files

- `config.yaml` — main configuration for collector behavior
- `secrets.yaml` — SSH credentials used by the scanner (protect with file permissions)
- `inventory.json` — Ansible-style inventory with `_meta.hostvars`

Keep secrets out of source control and secure `secrets.yaml` with restrictive permissions.
