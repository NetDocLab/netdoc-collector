"""
Optional API sender.

Reads the generated YAML file and POSTs it to a backend endpoint
using Bearer token authentication.

Called only when --api-token is provided on the CLI.
"""

import logging
import yaml
import requests

logger = logging.getLogger(__name__)


def send_to_api(yaml_path: str, api_url: str, token: str, timeout: int = 30) -> None:
    """
    Send the discovery YAML to a remote backend via HTTP POST.

    Args:
        yaml_path: path to the local YAML file produced by the aggregator
        api_url:   full endpoint URL, e.g. https://backend.example.com/api/v1/discovery
        token:     Bearer token for authentication
        timeout:   HTTP request timeout in seconds
    """
    with open(yaml_path) as f:
        payload = yaml.safe_load(f)

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    logger.info('Sending discovery data to %s', api_url)

    response = requests.post(
        url=api_url,
        json=payload,
        headers=headers,
        timeout=timeout,
    )

    if response.ok:
        logger.info('API response: %s %s', response.status_code, response.reason)
    else:
        logger.error(
            'API request failed: %s %s — %s',
            response.status_code,
            response.reason,
            response.text[:200],
        )
        response.raise_for_status()
