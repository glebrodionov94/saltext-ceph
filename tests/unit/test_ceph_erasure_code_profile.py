"""Erasure-code profile controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_erasure_code_profile as execution
from saltext.ceph.utils.ceph import erasure_code_profile
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_erasure_code_profile as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(201, None)
    return client


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


def test_list_uses_api_v1(client):
    client.request.return_value = APIResponse(200, [{"name": "ec42", "k": 4, "m": 2}])
    result = erasure_code_profile.list_(client)
    assert result.data == [{"name": "ec42", "k": 4, "m": 2}]
    client.request.assert_called_once_with("GET", "/api/erasure_code_profile", api_version="1.0")


@pytest.mark.parametrize("payload", [None, {}, ["ec42"], [{"name": "ec42"}, None]])
def test_list_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        erasure_code_profile.list_(client)


def test_get_returns_mapping(client):
    client.request.return_value = APIResponse(200, {"name": "ec42", "k": 4, "m": 2})
    result = erasure_code_profile.get(client, "ec42")
    assert result.data["name"] == "ec42"
    client.request.assert_called_once_with(
        "GET", "/api/erasure_code_profile/ec42", api_version="1.0"
    )


def test_get_rejects_invalid_response(client):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        erasure_code_profile.get(client, "ec42")


def test_create_accepts_plugin_specific_mapping(client):
    erasure_code_profile.create(
        client,
        "ec42",
        {
            "plugin": "jerasure",
            "k": 4,
            "m": 2,
            "crush-failure-domain": "host",
            "crush-device-class": "ssd",
        },
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/erasure_code_profile",
        api_version="1.0",
        data={
            "name": "ec42",
            "plugin": "jerasure",
            "k": 4,
            "m": 2,
            "crush-failure-domain": "host",
            "crush-device-class": "ssd",
        },
    )


def test_create_allows_server_defaults(client):
    erasure_code_profile.create(client, "ec-defaults")
    assert client.request.call_args.kwargs["data"] == {"name": "ec-defaults"}


@pytest.mark.parametrize(
    "name,settings",
    [
        ("bad/name", {}),
        ("ec42", []),
        ("ec42", {"bad key": "value"}),
        ("ec42", {"name": "other"}),
        ("ec42", {"force": True}),
        ("ec42", {"plugin": ""}),
        ("ec42", {"k": True}),
        ("ec42", {"k": None}),
        ("ec42", {"layout": [2, 1]}),
        ("ec42", {"ratio": float("inf")}),
    ],
)
def test_create_rejects_invalid_payload_before_http(client, name, settings):
    with pytest.raises(ConfigurationError):
        erasure_code_profile.create(client, name, settings)
    client.request.assert_not_called()


def test_delete_uses_api_v1(client):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        erasure_code_profile.delete(client, "ec42")
    client.request.assert_not_called()
    erasure_code_profile.delete(client, "ec42", confirm=True)
    client.request.assert_called_once_with(
        "DELETE", "/api/erasure_code_profile/ec42", api_version="1.0"
    )


@pytest.mark.parametrize("operation", ["get", "delete"])
def test_name_validation_happens_before_http(client, operation):
    with pytest.raises(ConfigurationError):
        getattr(erasure_code_profile, operation)(client, "bad/profile")
    client.request.assert_not_called()
