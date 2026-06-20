import os
from ipaddress import IPv4Network

import pytest
from apps.core.models import Tenant
from django.contrib.auth import get_user_model
from netdoc_sdk.client import NetDocClient
from rest_framework.authtoken.models import Token


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
            'inventory': {
                '_meta': {
                    'hostvars': {
                        NETDOC_DEVICE_ADDRESS: {
                            'ansible_host': NETDOC_DEVICE_ADDRESS,
                            'ansible_password': NETDOC_DEVICE_PASSWORD,
                            'ansible_port': 22,
                            'ansible_user': NETDOC_DEVICE_USERNAME,
                            'netdoc_plugin': 'netmiko:cisco:ios:ssh',
                            'netmiko_device_type': 'cisco_ios',
                        }
                    }
                },
                'all': {'hosts': [NETDOC_DEVICE_ADDRESS]},
            },
        }
    return {'collector': {}, 'scan': {}, 'inventory': {}}


def skip_ios_device_tests():
    return not _get_ios_device().get('scan')


@pytest.fixture()
def ios_device():
    return _get_ios_device()


@pytest.fixture
def admin_client(db, live_server):
    username = 'conftest-admin'
    password = '986629a7ca89202a3ef2ae1dd9d5fb37'
    User = get_user_model()

    # Create user within a tenant
    tenant, _created = Tenant.objects.get_or_create(name='conftest-tenant')
    user = User.objects.create_user(
        username=username, password=password, tenant=tenant, role='admin'
    )

    # Create token
    token, _ = Token.objects.get_or_create(user=user)

    return NetDocClient(base_url=live_server.url, token=token.key)


@pytest.fixture
def collector_client(db, live_server):
    username = 'conftest-collector'
    password = '0709fc937909d63b851fa5bd4437e33b'
    User = get_user_model()

    # Create user within a tenant
    tenant, _created = Tenant.objects.get_or_create(name='conftest-tenant')
    user = User.objects.create_user(
        username=username, password=password, tenant=tenant, role='collector'
    )

    # Create token
    token, _ = Token.objects.get_or_create(user=user)

    return NetDocClient(base_url=live_server.url, token=token.key)
