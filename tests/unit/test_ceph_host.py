"""Host controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_host as execution
from saltext.ceph.utils.ceph import host
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_host as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, None)
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


def test_list_uses_all_hosts_default_and_api_v1_3(client):
    client.request.return_value = APIResponse(200, [{"hostname": "node1"}])
    result = host.list_(client)
    assert result.data == [{"hostname": "node1"}]
    client.request.assert_called_once_with(
        "GET",
        "/api/host",
        api_version="1.3",
        params={
            "facts": False,
            "offset": 0,
            "limit": -1,
            "search": "",
            "sort": "+hostname",
            "include_service_instances": True,
        },
    )


def test_list_serializes_sources_and_filters(client):
    client.request.return_value = APIResponse(200, [])
    host.list_(
        client,
        ["orchestrator", "ceph"],
        facts=True,
        offset=5,
        limit=10,
        search="node",
        sort="-hostname",
        include_service_instances=False,
    )
    assert client.request.call_args.kwargs["params"] == {
        "sources": "orchestrator,ceph",
        "facts": True,
        "offset": 5,
        "limit": 10,
        "search": "node",
        "sort": "-hostname",
        "include_service_instances": False,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sources": "ceph"},
        {"sources": ["unknown"]},
        {"facts": "true"},
        {"offset": -1},
        {"limit": -2},
        {"search": "bad\nvalue"},
        {"sort": "status"},
        {"include_service_instances": 1},
    ],
)
def test_list_rejects_invalid_filters(client, kwargs):
    with pytest.raises(ConfigurationError):
        host.list_(client, **kwargs)
    client.request.assert_not_called()


def test_get_uses_api_v1_2(client):
    client.request.return_value = APIResponse(200, {"hostname": "node1"})
    assert host.get(client, "node1").data["hostname"] == "node1"
    client.request.assert_called_once_with("GET", "/api/host/node1", api_version="1.2")


def test_create_uses_experimental_api_and_omits_unspecified_values(client):
    host.create(client, "node1", "10.0.0.11", ["storage", "_admin"], maintenance=True)
    client.request.assert_called_once_with(
        "POST",
        "/api/host",
        api_version="0.1",
        data={
            "hostname": "node1",
            "addr": "10.0.0.11",
            "labels": ["storage", "_admin"],
            "status": "maintenance",
        },
    )


def test_set_labels_supports_removing_every_label(client):
    host.set_labels(client, "node1", [])
    assert client.request.call_args.kwargs == {
        "api_version": "0.1",
        "data": {"update_labels": True, "labels": []},
    }


def test_toggle_maintenance_sends_force_only_when_true(client):
    host.toggle_maintenance(client, "node1", force=True)
    assert client.request.call_args.kwargs["data"] == {"maintenance": True, "force": True}


def test_drain_uses_explicit_action_payload(client):
    host.drain(client, "node1")
    assert client.request.call_args.kwargs["data"] == {"drain": True}


def test_delete_uses_default_api(client):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        host.delete(client, "node1")
    client.request.assert_not_called()
    host.delete(client, "node1", confirm=True)
    client.request.assert_called_once_with("DELETE", "/api/host/node1", api_version="1.0")


@pytest.mark.parametrize(
    "function,suffix,payload",
    [
        (host.devices, "devices", []),
        (host.smart, "smart", {}),
        (host.daemons, "daemons", []),
    ],
)
def test_read_subresources(client, function, suffix, payload):
    client.request.return_value = APIResponse(200, payload)
    function(client, "node1")
    client.request.assert_called_once_with("GET", f"/api/host/node1/{suffix}", api_version="1.0")


def test_inventory_supports_explicit_refresh(client):
    client.request.return_value = APIResponse(200, {"name": "node1", "devices": []})
    host.inventory(client, "node1", refresh=True)
    client.request.assert_called_once_with(
        "GET",
        "/api/host/node1/inventory",
        api_version="1.0",
        params={"refresh": True},
    )


def test_identify_device_bounds_duration(client):
    host.identify_device(client, "node1", "/dev/sdb", duration=15)
    client.request.assert_called_once_with(
        "POST",
        "/api/host/node1/identify_device",
        api_version="1.0",
        data={"device": "/dev/sdb", "duration": 15},
    )


@pytest.mark.parametrize(
    "call,args",
    [
        (host.get, ("bad/host",)),
        (host.create, ("node1", None, ["bad label"])),
        (host.create, ("node1", None, ["storage", "storage"])),
        (host.toggle_maintenance, ("node1", "true")),
        (host.inventory, ("node1", "true")),
        (host.identify_device, ("node1", "", 10)),
        (host.identify_device, ("node1", "/dev/sdb", 0)),
        (host.identify_device, ("node1", "/dev/sdb", 3601)),
    ],
)
def test_operations_reject_invalid_input_before_http(client, call, args):
    with pytest.raises(ConfigurationError):
        call(client, *args)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "call,payload",
    [
        (host.list_, {}),
        (lambda client: host.get(client, "node1"), []),
        (lambda client: host.devices(client, "node1"), {}),
        (lambda client: host.smart(client, "node1"), []),
        (lambda client: host.inventory(client, "node1"), []),
        (lambda client: host.daemons(client, "node1"), {}),
    ],
)
def test_reads_reject_invalid_response(client, call, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        call(client)
