# NetDoc - collector module

## Config file

```yaml
inventory: inventory.json
output: ./output
workers: 10
# backend:
#   url: http://localhost/api/v1
#   verify: false
#   timeout: 30
```

## Inventory file

```json
{
    "_meta": {
        "hostvars": {
            "eve-ng.example.com": {
                "ansible_connection": "local",
                "ansible_host": "172.24.0.1",
                "ansible_python_interpreter": "/root/eveng-cli/.venv/bin/python"
            },
            "mgmtswitch1.example.com": {
                "ansible_host": "172.25.10.2",
                "ansible_connection": "ansible.netcommon.network_cli",
                "ansible_network_os": "cisco.ios.ios",
                "ansible_user": "admin",
                "ansible_password": "Passw0rd!",
                "ansible_become": "no",
                "ansible_become_method": "enable",
                "ansible_become_password": "enable_secret",
                "netmiko_device_type": "cisco_ios",
                "netdoc_plugin": "netmiko:cisco:ios"
            }
        }
    },
    "all": {
        "hosts": [
            "eve-ng.example.com",
            "mgmtswitch1.example.com"
        ]
    },
    "site-lab": {
        "hosts": [
            "mgmtswitch1.example.com"
        ]
    }
}
```
