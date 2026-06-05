# NetDoc Collector

NetDoc Collector is the network discovery/collector component used by NetDoc. It runs probes against network devices (via SSH/telnet/HTTPS) and produces a per-device raw payload in a format ingestible by the NetDoc backend.

This README provides quick installation and usage examples for both stand-alone and managed (backend-driven) modes, plus example files for `inventory`, `config`, and `secrets`.

## Installation

Install in editable mode for development:

```bash
pip install netdoc-collector
```

You can run the CLI using the console script `netdoc-collector` (installed by the package):

```bash
netdoc-collector --help
```

## Modes

- Stand-alone: read a local Ansible-style JSON inventory and run collection locally, writing output under `output/`.
- Managed: poll the NetDoc backend for discovery jobs, run collection and push raw payloads back to the backend.

## Example: `config.yaml`

Minimal configuration options used by the collector.

```yaml
inventory: inventory.json  # default inventory file (stand-alone)
output: ./output           # directory to write discovery snapshots
workers: 5                 # number of worker threads for Nornir
cmd_timeout: 240           # per-command timeout (seconds)
retention: 5               # keep last N snapshots locally

# Backend configuration for managed mode
backend:
    url: https://netdoc.example.com/api/v1
    timeout: 120           # timeout for requests to the backend
    token: null            # optional, can be provided via env or CLI
    verify: true           # whether to verify TLS for backend
```

## Example: `secrets.yaml`

This file stores collector credentials used by the built-in scanner to attempt SSH logins for OS/device detection. Keep it readable only by the collector service (file permissions) and never commit real secrets to source control.

```yaml
credentials:
    - label: default
        username: admin
        password: Passw0rd!
        secret: enable_secret  # optional enable/privileged password
    - label: readonly
        username: readonly
        password: read0nly
```

## Example: `inventory.json` (Ansible dynamic inventory format)

The collector expects an Ansible-style JSON inventory with `_meta.hostvars`. At minimum each host should provide `ansible_host` and `netdoc_plugin` so discovery knows which plugin to use.

```json
{
    "_meta": {
        "hostvars": {
            "switch1.example.com": {
                "ansible_host": "192.0.2.10",
                "ansible_user": "admin",
                "ansible_password": "Passw0rd!",
                "netmiko_device_type": "cisco_ios",
            },
            "linux-host.example.com": {
                "ansible_host": "192.0.2.20",
                "ansible_user": "ubuntu",
                "ansible_password": "secret",
                "netmiko_device_type": "linux",
            }
        }
    },
    "all": {
        "hosts": [
            "switch1.example.com",
            "linux-host.example.com"
        ]
    }
}
```

## Usage examples

Stand-alone mode (use a local inventory):

```bash
# read inventory.json and write outputs to ./output
netdoc-collector -i inventory.json -c config.yaml

# or override values on the CLI
netdoc-collector -i inventory.json -o ./output -w 10
```

Managed mode (claim jobs from backend and push results):

```bash
# provide backend URL and token (env or CLI)
export NETDOC_TOKEN="<your-api-token>"
netdoc-collector --url https://netdoc.example.com --token $NETDOC_TOKEN

# you can also pass token and url via CLI flags
netdoc-collector --url https://netdoc.example.com --token mytoken --workers 8
```

Notes:
- When running in managed mode, the collector will attempt to login to the backend to claim discovery jobs. Provide a valid `backend.url` and API token via `config.yaml`, environment variable `NETDOC_TOKEN`, or the `--token` CLI flag.
- Keep `secrets.yaml` permissions restrictive (e.g. `chmod 600 secrets.yaml`).

## Output

Discovery snapshots are written under the configured `output` directory in timestamped folders. Each host will have a subdirectory with `.json` and `.raw` files containing command outputs and parsed results.

## Contributing

See the project repository for contribution guidelines and coding standards.
