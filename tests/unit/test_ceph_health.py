"""Health controller operations and response validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_health as execution
from saltext.ceph.utils.ceph import health
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_health as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, {})
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


@pytest.mark.parametrize(
    "function,endpoint",
    [
        (health.full, "full"),
        (health.minimal, "minimal"),
        (health.capacity, "get_cluster_capacity"),
        (health.snapshot, "snapshot"),
    ],
)
def test_mapping_operations_use_api_v1(client, function, endpoint):
    result = function(client)
    assert result.data == {}
    client.request.assert_called_once_with("GET", f"/api/health/{endpoint}", api_version="1.0")


@pytest.mark.parametrize(
    "function", [health.full, health.minimal, health.capacity, health.snapshot]
)
def test_mapping_operations_reject_invalid_response(client, function):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        function(client)


def test_fsid_requires_nonempty_string(client):
    client.request.return_value = APIResponse(200, "cluster-fsid")
    assert health.fsid(client).data == "cluster-fsid"
    client.request.assert_called_once_with("GET", "/api/health/get_cluster_fsid", api_version="1.0")


@pytest.mark.parametrize("payload", [None, "", {}, 123])
def test_fsid_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        health.fsid(client)


@pytest.mark.parametrize("enabled", [True, False])
def test_telemetry_enabled_requires_boolean(client, enabled):
    client.request.return_value = APIResponse(200, enabled)
    assert health.telemetry_enabled(client).data is enabled
    client.request.assert_called_once_with(
        "GET", "/api/health/get_telemetry_status", api_version="1.0"
    )


@pytest.mark.parametrize("payload", [None, 0, "false", {}])
def test_telemetry_enabled_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        health.telemetry_enabled(client)
