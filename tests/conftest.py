import os
from ipaddress import IPv4Network
import pytest


def _get_ios_device():
    NETDOC_DEVICE_ADDRESS = os.getenv('NETDOC_DEVICE_ADDRESS', None)
    NETDOC_DEVICE_USERNAME = os.getenv('NETDOC_DEVICE_USERNAME', None)
    NETDOC_DEVICE_PASSWORD = os.getenv('NETDOC_DEVICE_PASSWORD', None)

    if NETDOC_DEVICE_ADDRESS and NETDOC_DEVICE_USERNAME and NETDOC_DEVICE_PASSWORD:
        return {
            'collector': {
                'address': NETDOC_DEVICE_ADDRESS,
                'username': NETDOC_DEVICE_USERNAME,
                'password': NETDOC_DEVICE_PASSWORD,
            },
            'scan': {
                'credentials': [
                    {
                        'label': 'Test Credential',
                        'username': NETDOC_DEVICE_USERNAME,
                        'password': NETDOC_DEVICE_PASSWORD,
                    }
                ],
                'networks': [IPv4Network(f'{NETDOC_DEVICE_ADDRESS}/32')],
                'ports': [22],
            },
        }
    return {'collector': {}, 'scan': {}}


@pytest.fixture()
def ios_device():
    return _get_ios_device()


def skip_ios_device_tests():
    if _get_ios_device().get('scan'):
        return False
    return True
