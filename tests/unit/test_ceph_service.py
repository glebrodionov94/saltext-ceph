"""Service controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_service as execution
from saltext.ceph.utils.ceph import service
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_service as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(202, {"name": "service/create"})
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


def test_list_uses_api_v2_and_requests_all_services_by_default(client):
    client.request.return_value = APIResponse(
        200,
        [{"service_name": "mgr", "service_type": "mgr", "status": {"running": 2}}],
        {"x-total-count": "1"},
    )
    result = service.list_(client)
    assert result.data[0]["service_name"] == "mgr"
    assert result.headers == {"x-total-count": "1"}
    client.request.assert_called_once_with(
        "GET",
        "/api/service",
        api_version="2.0",
        params={
            "offset": 0,
            "limit": -1,
            "search": "",
            "sort": "+service_name",
        },
    )


def test_list_passes_filter_pagination_search_and_sort(client):
    client.request.return_value = APIResponse(200, [])
    service.list_(
        client,
        service_name="rgw.realm.zone",
        offset=5,
        limit=10,
        search="realm",
        sort="-status.running",
    )
    assert client.request.call_args.kwargs["params"] == {
        "service_name": "rgw.realm.zone",
        "offset": 5,
        "limit": 10,
        "search": "realm",
        "sort": "-status.running",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"service_name": "bad/name"},
        {"offset": True},
        {"offset": -1},
        {"limit": True},
        {"limit": -2},
        {"search": None},
        {"search": "x" * 256},
        {"search": "bad\nsearch"},
        {"sort": "status.health"},
        {"sort": "service_name desc"},
    ],
)
def test_list_rejects_invalid_query_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        service.list_(client, **kwargs)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, {}, ["mgr"], [{"service_name": "mgr"}, None]])
def test_list_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        service.list_(client)


def test_get_uses_api_v1_and_returns_mapping(client):
    client.request.return_value = APIResponse(
        200, {"service_name": "rgw.realm.zone", "service_type": "rgw"}
    )
    result = service.get(client, "rgw.realm.zone")
    assert result.data["service_type"] == "rgw"
    client.request.assert_called_once_with("GET", "/api/service/rgw.realm.zone", api_version="1.0")


def test_get_rejects_non_mapping_response(client):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        service.get(client, "mgr")


def test_known_types_uses_api_v1_and_returns_string_list(client):
    client.request.return_value = APIResponse(200, ["mgr", "node-exporter", "rgw"])
    result = service.known_types(client)
    assert result.data == ["mgr", "node-exporter", "rgw"]
    client.request.assert_called_once_with("GET", "/api/service/known_types", api_version="1.0")


@pytest.mark.parametrize("payload", [None, {}, ["mgr", None], [""]])
def test_known_types_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        service.known_types(client)


def test_daemons_uses_api_v1_and_returns_mapping_list(client):
    client.request.return_value = APIResponse(
        200, [{"daemon_name": "rgw.realm.zone.host1.abc", "status": 1}]
    )
    result = service.daemons(client, "rgw.realm.zone")
    assert result.data[0]["status"] == 1
    client.request.assert_called_once_with(
        "GET", "/api/service/rgw.realm.zone/daemons", api_version="1.0"
    )


def test_daemons_rejects_invalid_response(client):
    client.request.return_value = APIResponse(200, {})
    with pytest.raises(ProtocolError):
        service.daemons(client, "mgr")


def test_create_sends_structured_service_spec_without_mutating_input(client):
    service_spec = {
        "service_type": "rgw",
        "service_id": "realm.zone",
        "placement": {"hosts": ["node1", "node2"]},
        "networks": ["10.20.0.0/24"],
        "custom_configs": [
            {"mount_path": "/etc/rgw/example.conf", "content": "[client]\nkey = value\n"}
        ],
    }
    original = service_spec.copy()
    service.create(client, "rgw.realm.zone", service_spec)
    assert service_spec == original
    client.request.assert_called_once_with(
        "POST",
        "/api/service",
        api_version="1.0",
        data={
            "service_name": "rgw.realm.zone",
            "service_spec": service_spec,
        },
    )


def test_create_accepts_exported_service_name_identity(client):
    service.create(
        client,
        "prometheus",
        {"service_name": "prometheus", "placement": {"count": 1}},
    )
    assert client.request.call_args.kwargs["data"]["service_spec"] == {
        "service_name": "prometheus",
        "placement": {"count": 1},
    }


def test_update_sends_only_service_spec_in_body(client):
    service_spec = {
        "service_type": "rgw",
        "service_id": "realm.zone",
        "placement": {"count": 3, "label": "rgw"},
    }
    service.update(client, "rgw.realm.zone", service_spec)
    client.request.assert_called_once_with(
        "PUT",
        "/api/service/rgw.realm.zone",
        api_version="1.0",
        data={"service_spec": service_spec},
    )


@pytest.mark.parametrize(
    "service_name,service_spec",
    [
        ("mgr", None),
        ("mgr", {}),
        ("mgr", []),
        ("mgr", {"placement": {"count": 1}}),
        ("rgw.foo", {"service_id": "foo"}),
        ("mgr", {"service_type": "bad.type"}),
        ("rgw.foo", {"service_type": "rgw", "service_id": "bad/id"}),
        (
            "rgw.foo",
            {"service_type": "rgw", "service_id": "foo", "service_name": "rgw.bar"},
        ),
        ("rgw.bar", {"service_type": "rgw", "service_id": "foo"}),
        ("mgr", {"service_type": "mgr", "placement": ("node1",)}),
        ("mgr", {"service_type": "mgr", "count": float("inf")}),
        ("mgr", {"service_type": "mgr", "placement": {"bad\nkey": 1}}),
    ],
)
@pytest.mark.parametrize("operation", ["create", "update"])
def test_writes_reject_invalid_service_spec_before_http(
    client, operation, service_name, service_spec
):
    with pytest.raises(ConfigurationError):
        getattr(service, operation)(client, service_name, service_spec)
    client.request.assert_not_called()


def test_delete_uses_api_v1(client):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        service.delete(client, "rgw.realm.zone")
    client.request.assert_not_called()
    service.delete(client, "rgw.realm.zone", confirm=True)
    client.request.assert_called_once_with(
        "DELETE", "/api/service/rgw.realm.zone", api_version="1.0"
    )


@pytest.mark.parametrize("operation", ["get", "daemons", "delete"])
@pytest.mark.parametrize("service_name", ["", "bad/name", "bad name", 42, "x" * 256])
def test_resource_operations_validate_service_name_before_http(client, operation, service_name):
    with pytest.raises(ConfigurationError):
        getattr(service, operation)(client, service_name)
    client.request.assert_not_called()
