"""Cluster controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_cluster as execution
from saltext.ceph.utils.ceph import cluster
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_cluster as wrapper


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


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, {})
    return client


def test_status_uses_experimental_api_version(client):
    client.request.return_value = APIResponse(200, {"status": "POST_INSTALLED"})
    result = cluster.status(client)
    assert result.data == {"status": "POST_INSTALLED"}
    client.request.assert_called_once_with("GET", "/api/cluster", api_version="0.1")


@pytest.mark.parametrize("payload", [None, {}, {"status": "READY"}, "POST_INSTALLED"])
def test_status_rejects_unexpected_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        cluster.status(client)


def test_set_status_normalizes_enum_name(client):
    cluster.set_status(client, "post_installed")
    client.request.assert_called_once_with(
        "PUT",
        "/api/cluster",
        api_version="0.1",
        data={"status": "POST_INSTALLED"},
    )


@pytest.mark.parametrize("value", [None, "", "READY", 1])
def test_set_status_rejects_invalid_value_before_http(client, value):
    with pytest.raises(ConfigurationError):
        cluster.set_status(client, value)
    client.request.assert_not_called()


def test_upgrade_list_sends_explicit_boolean_filters(client):
    client.request.return_value = APIResponse(
        200, {"image": "quay.io/ceph/ceph", "versions": ["18.2.7"]}
    )
    result = cluster.upgrade_list(
        client, tags=True, image="quay.io/ceph/ceph", show_all_versions=False
    )
    assert result.data["versions"] == ["18.2.7"]
    client.request.assert_called_once_with(
        "GET",
        "/api/cluster/upgrade",
        api_version="1.0",
        params={
            "tags": True,
            "show_all_versions": False,
            "image": "quay.io/ceph/ceph",
        },
    )


def test_upgrade_list_accepts_legacy_list_response(client):
    client.request.return_value = APIResponse(200, ["17.2.7", "18.2.7"])
    assert cluster.upgrade_list(client).data == ["17.2.7", "18.2.7"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"tags": "true"},
        {"show_all_versions": 1},
        {"image": "https://quay.io/ceph/ceph"},
        {"image": "quay.io/ceph/ceph latest"},
    ],
)
def test_upgrade_list_rejects_invalid_filters_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        cluster.upgrade_list(client, **kwargs)
    client.request.assert_not_called()


def test_upgrade_list_rejects_invalid_response(client):
    client.request.return_value = APIResponse(200, "18.2.7")
    with pytest.raises(ProtocolError):
        cluster.upgrade_list(client)


def test_upgrade_status_requires_mapping(client):
    client.request.return_value = APIResponse(200, {"in_progress": False})
    assert cluster.upgrade_status(client).data == {"in_progress": False}
    client.request.assert_called_once_with("GET", "/api/cluster/upgrade/status", api_version="1.0")

    client.reset_mock()
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        cluster.upgrade_status(client)


def test_upgrade_start_supports_scoped_version_upgrade(client):
    cluster.upgrade_start(
        client,
        version="18.2.7",
        daemon_types=["mgr", "mon"],
        host_placement="host1 host2",
        limit=2,
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/cluster/upgrade/start",
        api_version="1.0",
        data={
            "version": "18.2.7",
            "daemon_types": ["mgr", "mon"],
            "host_placement": "host1 host2",
            "limit": 2,
        },
    )


def test_upgrade_start_supports_image_and_services(client):
    cluster.upgrade_start(
        client,
        image="registry.example:5000/ceph/ceph@sha256:abc123",
        services=["rgw.site-a"],
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/cluster/upgrade/start",
        api_version="1.0",
        data={
            "image": "registry.example:5000/ceph/ceph@sha256:abc123",
            "services": ["rgw.site-a"],
        },
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"image": "quay.io/ceph/ceph:v18", "version": "18.2.7"},
        {"version": "reef"},
        {"version": "18.2.7", "daemon_types": "mgr"},
        {"version": "18.2.7", "daemon_types": ["mgr", "mgr"]},
        {"version": "18.2.7", "daemon_types": ["mgr"], "services": ["mgr"]},
        {"version": "18.2.7", "services": ["rgw/site"]},
        {"version": "18.2.7", "host_placement": "host1\nhost2"},
        {"version": "18.2.7", "limit": True},
        {"version": "18.2.7", "limit": 0},
    ],
)
def test_upgrade_start_rejects_invalid_payload_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        cluster.upgrade_start(client, **kwargs)
    client.request.assert_not_called()


@pytest.mark.parametrize("action", ["pause", "resume", "stop"])
def test_upgrade_actions_use_empty_put(client, action):
    getattr(cluster, f"upgrade_{action}")(client)
    client.request.assert_called_once_with(
        "PUT", f"/api/cluster/upgrade/{action}", api_version="1.0"
    )
    client.reset_mock()
