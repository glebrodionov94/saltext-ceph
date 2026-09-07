"""Certificate controller operations and validation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.utils.ceph import certificates
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, [])
    return client


def test_list_omits_default_filters(client):
    result = certificates.list_(client)
    assert result.data == []
    client.request.assert_called_once_with(
        "GET", "/api/service/certificate", api_version="1.0", params={}
    )


def test_list_normalizes_and_sends_supported_filters(client):
    certificates.list_(client, "EXPIRING", "SERVICE", "RGW*", True)
    client.request.assert_called_once_with(
        "GET",
        "/api/service/certificate",
        api_version="1.0",
        params={
            "status": "expiring",
            "scope": "service",
            "service_type": "rgw*",
            "include_cephadm_signed": True,
        },
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "unknown"},
        {"scope": "cluster"},
        {"service_type": "rgw,status=expired"},
        {"service_type": ""},
        {"include_cephadm_signed": "true"},
    ],
)
def test_invalid_filters_fail_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        certificates.list_(client, **kwargs)
    client.request.assert_not_called()


def test_get_service_certificate(client):
    client.request.return_value = APIResponse(200, {"cert_name": "rgw_ssl_cert", "status": "valid"})
    result = certificates.get(client, "rgw.site-a")
    assert result.data["status"] == "valid"
    client.request.assert_called_once_with(
        "GET", "/api/service/certificate/rgw.site-a", api_version="1.0"
    )


@pytest.mark.parametrize("service_name", ["", "rgw/site", "rgw?site", " rgw.site"])
def test_invalid_service_name_fails_before_http(client, service_name):
    with pytest.raises(ConfigurationError):
        certificates.get(client, service_name)
    client.request.assert_not_called()


def test_root_ca_accepts_pem_certificate(client):
    pem = "-----BEGIN CERTIFICATE-----\npublic\n-----END CERTIFICATE-----"
    client.request.return_value = APIResponse(200, pem)
    assert certificates.root_ca(client).data == pem
    client.request.assert_called_once_with(
        "GET", "/api/service/certificate/root-ca", api_version="1.0"
    )


@pytest.mark.parametrize(
    "operation,payload", [("list", {}), ("list", ["bad"]), ("get", []), ("root", "bad")]
)
def test_unexpected_response_shapes_are_rejected(client, operation, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        if operation == "list":
            certificates.list_(client)
        elif operation == "get":
            certificates.get(client, "rgw.site")
        else:
            certificates.root_ca(client)
