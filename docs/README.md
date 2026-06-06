# NetDoc Collector

NetDoc Collector is the network discovery and collector component used by NetDoc. It runs probes against network devices (via SSH/telnet/HTTPS) and creates per-device raw payloads that the NetDoc backend can ingest.

This repository uses `mkdocs` with the root `README.md` as the homepage and `mkdocstrings` to generate API reference content from `src/netdoc_collector`.

## Installation

Recommended install for development:

```bash
poetry install
```

Install the package in editable mode if you want the CLI available immediately:

```bash
poetry run pip install -e .
```

Run the command-line tool:

```bash
poetry run netdoc-collector --help
```

## Modes

- **Stand-alone mode**: read a local Ansible-style JSON inventory and collect data locally.
- **Managed mode**: claim jobs from the NetDoc backend, run collection, and push results back.

## Configuration example: `config.yaml`

```yaml
inventory: inventory.json
output: ./output
workers: 5
cmd_timeout: 240
retention: 5

backend:
  url: https://netdoc.example.com/api/v1
  timeout: 120
  token: null
  verify: true
```

## Secrets example: `secrets.yaml`

This file stores credentials used by the collector's scanner and collection logic. Keep it out of version control and protect it with restrictive file permissions.

```yaml
credentials:
  - label: default
    username: admin
    password: Passw0rd!
    secret: enable_secret
  - label: readonly
    username: readonly
    password: read0nly
```

## Inventory example: `inventory.json`

The collector accepts Ansible-style JSON inventory with `_meta.hostvars` and host-specific connection details.

```json
{
  "_meta": {
    "hostvars": {
      "switch1.example.com": {
        "ansible_host": "192.0.2.10",
        "ansible_user": "admin",
        "ansible_password": "Passw0rd!",
        "netmiko_device_type": "cisco_ios"
      },
      "linux-host.example.com": {
        "ansible_host": "192.0.2.20",
        "ansible_user": "ubuntu",
        "ansible_password": "secret",
        "netmiko_device_type": "linux"
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

### Stand-alone mode

```bash
netdoc-collector -i inventory.json -c config.yaml
netdoc-collector -i inventory.json -o ./output -w 10
```

### Scanner mode

```bash
netdoc-collector -s -n 172.25.82.2/32
```

### Managed mode

```bash
export NETDOC_TOKEN="<your-api-token>"
netdoc-collector --url https://netdoc.example.com --token "$NETDOC_TOKEN"
```

Or pass credentials directly:

```bash
netdoc-collector --url https://netdoc.example.com --token mytoken --workers 8
```

## Output

Discovery snapshots are written into the configured `output` directory in timestamped folders. Each host gets a subdirectory with JSON payloads and raw command output files.

## Developer quickstart

```bash
git clone https://github.com/NetDocLab/netdoc-collector.git
cd netdoc-collector
poetry install
pre-commit install
pre-commit install --hook-type commit-msg
```

### Run tests

```bash
poetry run pytest
```

### Build documentation locally

```bash
poetry run mkdocs build --strict
poetry run mkdocs serve -a 127.0.0.1:8000
```

### Formatting and linting

```bash
poetry run ruff check .
poetry run ruff format .
```

## Documentation

This project publishes docs from the root `README.md` and reference pages generated from source code using `mkdocstrings`.

## Contributing

See `CONTRIBUTING.md` for contribution guidelines, branch conventions, and CI requirements.
