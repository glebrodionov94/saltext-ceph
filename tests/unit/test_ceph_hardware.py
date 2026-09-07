"""Hardware controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_hardware as execution
from saltext.ceph.utils.ceph import hardware
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_hardware as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, {"total": {}, "host": {}})
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


def test_summary_uses_experimental_api_and_array_filters(client):
    result = hardware.summary(client, ["storage", "memory"], ["node1", "node2"])
    assert result.data == {"total": {}, "host": {}}
    client.request.assert_called_once_with(
        "GET",
        "/api/hardware/summary",
        api_version="0.1",
        params={
            "categories": ["storage", "memory"],
            "hostname": ["node1", "node2"],
        },
    )


def test_summary_without_filters_sends_empty_query(client):
    hardware.summary(client)
    assert client.request.call_args.kwargs["params"] == {}


@pytest.mark.parametrize(
    "categories,hostnames",
    [
        ([], None),
        ("memory", None),
        (["memory", "memory"], None),
        (["unknown"], None),
        (None, []),
        (None, "node1"),
        (None, ["bad/host"]),
        (None, ["node1", "node1"]),
    ],
)
def test_summary_rejects_invalid_filters(client, categories, hostnames):
    with pytest.raises(ConfigurationError):
        hardware.summary(client, categories, hostnames)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, [], "OK"])
def test_summary_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        hardware.summary(client)
