"""Dashboard telemetry controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_telemetry as execution
from saltext.ceph.utils.ceph import telemetry
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_telemetry as wrapper


@pytest.fixture
def client():
    return Mock()


def test_wrapper_exports_execution_functions_with_matching_signatures():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    assert names == {
        name
        for name, function in inspect.getmembers(wrapper, inspect.isfunction)
        if not name.startswith("_")
    }
    for name in names:
        assert inspect.signature(getattr(wrapper, name)) == inspect.signature(
            getattr(execution, name)
        )


def test_report_uses_collection_resource(client):
    payload = {"report": {"report_id": "anonymous"}, "device_report": {}}
    client.request.return_value = APIResponse(200, payload)
    assert telemetry.report(client).data == payload
    client.request.assert_called_once_with("GET", "/api/telemetry/report", api_version="1.0")


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"report": []}, {"report": {}, "device_report": "{}"}],
)
def test_report_rejects_invalid_protocol_shape(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        telemetry.report(client)


def test_enable_requires_and_sends_exact_license(client):
    client.request.return_value = APIResponse(200, None)
    result = telemetry.set_(client, True, telemetry.LICENSE)
    assert result.data == {"enabled": True}
    client.request.assert_called_once_with(
        "PUT",
        "/api/telemetry",
        api_version="1.0",
        data={"enable": True, "license_name": "sharing-1-0"},
    )


def test_disable_omits_license(client):
    client.request.return_value = APIResponse(200, None)
    result = telemetry.set_(client, False)
    assert result.data == {"enabled": False}
    client.request.assert_called_once_with(
        "PUT", "/api/telemetry", api_version="1.0", data={"enable": False}
    )


@pytest.mark.parametrize(
    "enable,license_name",
    [
        (True, None),
        (True, "wrong-license"),
        (False, telemetry.LICENSE),
        (1, telemetry.LICENSE),
    ],
)
def test_invalid_consent_fails_before_http(client, enable, license_name):
    with pytest.raises(ConfigurationError):
        telemetry.set_(client, enable, license_name)
    client.request.assert_not_called()
