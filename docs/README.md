# NetDoc Collector

NetDoc Collector is the discovery and data collection component used by NetDoc. It connects to network devices over SSH, Telnet, or HTTPS, runs vendor-specific commands, and stores the resulting raw data for downstream processing.

This repository uses MkDocs for documentation and MkDocstrings to generate API reference pages from the source code in src/netdoc_collector.

## Installation

For local development, install the project dependencies with Poetry:

```bash
poetry install
```

If you want the CLI to be available immediately in your environment, install the package in editable mode:

```bash
poetry run pip install -e .
```

Verify that the command-line interface is available:

```bash
poetry run netdoc-collector --help
```

## Modes

- Stand-alone mode: read a local Ansible-style JSON inventory and collect data from the listed devices.
- Managed mode: claim a discovery job from the NetDoc backend, collect the required data, and push the results back.

## Configuration example: config.yaml

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
  insecure: false
```

## Secrets example: secrets.yaml

Store credentials in this file for the scanner and collection logic. Keep it out of version control and protect it with restrictive file permissions.

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

## Inventory example: inventory.json

The collector accepts Ansible-style JSON inventory data with _meta.hostvars and host-specific connection details.

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

You can also provide the token directly on the command line:

```bash
netdoc-collector --url https://netdoc.example.com --token mytoken --workers 8
```

## Output

Discovery snapshots are written to the configured output directory in timestamped folders. Each host receives its own subdirectory containing JSON payloads and raw command output files.

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

The published documentation is built from this README and the API reference pages generated from the source code.

## Contributing

See CONTRIBUTING.md for contribution guidelines, branch conventions, and CI requirements.
