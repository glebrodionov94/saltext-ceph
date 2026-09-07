"""Daemon controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_daemon as execution
from saltext.ceph.utils.ceph import daemon
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_daemon as wrapper


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


def test_list_without_filter_uses_api_v1(client):
    client.request.return_value = APIResponse(200, [{"daemon_name": "mgr.node1"}])
    result = daemon.list_(client)
    assert result.data == [{"daemon_name": "mgr.node1"}]
    client.request.assert_called_once_with("GET", "/api/daemon", api_version="1.0", params={})


def test_list_sends_daemon_types_as_array_query(client):
    client.request.return_value = APIResponse(200, [])
    daemon.list_(client, ["mon", "rbd-mirror"])
    client.request.assert_called_once_with(
        "GET",
        "/api/daemon",
        api_version="1.0",
        params={"daemon_types": ["mon", "rbd-mirror"]},
    )


@pytest.mark.parametrize("value", [[], "mon", ["mon", "mon"], ["bad/type"], [1]])
def test_list_rejects_invalid_filters_before_http(client, value):
    with pytest.raises(ConfigurationError):
        daemon.list_(client, value)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, {}, ["mgr.node1"], [{"daemon_name": "mgr.x"}, None]])
def test_list_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        daemon.list_(client)


@pytest.mark.parametrize("action_name", ["START", "stop", "restart", "redeploy"])
def test_action_accepts_controller_actions(client, action_name):
    daemon.action(client, "rgw.site.node1.abcd", action_name)
    client.request.assert_called_once_with(
        "PUT",
        "/api/daemon/rgw.site.node1.abcd",
        api_version="0.1",
        data={"action": action_name.lower()},
    )
    client.reset_mock()


def test_redeploy_supports_explicit_container_image(client):
    daemon.action(
        client,
        "mgr.node1.abcd",
        "redeploy",
        container_image="quay.io/ceph/ceph@sha256:abc123",
    )
    client.request.assert_called_once_with(
        "PUT",
        "/api/daemon/mgr.node1.abcd",
        api_version="0.1",
        data={
            "action": "redeploy",
            "container_image": "quay.io/ceph/ceph@sha256:abc123",
        },
    )


@pytest.mark.parametrize("action_name", ["stop", "restart"])
def test_force_is_sent_only_when_enabled(client, action_name):
    daemon.action(client, "rgw.site.node1.abcd", action_name, force=True)
    assert client.request.call_args.kwargs["data"] == {
        "action": action_name,
        "force": True,
    }
    client.reset_mock()


@pytest.mark.parametrize(
    "daemon_name,action_name,container_image,force",
    [
        ("bad/name", "start", None, False),
        ("mgr.node1", "reload", None, False),
        ("mgr.node1", "start", "quay.io/ceph/ceph:v18", False),
        ("mgr.node1", "redeploy", "https://quay.io/ceph/ceph", False),
        ("mgr.node1", "redeploy", "", False),
        ("mgr.node1", "start", None, True),
        ("mgr.node1", "redeploy", None, True),
        ("mgr.node1", "stop", None, "true"),
    ],
)
def test_action_rejects_invalid_payload_before_http(
    client, daemon_name, action_name, container_image, force
):
    with pytest.raises(ConfigurationError):
        daemon.action(client, daemon_name, action_name, container_image, force)
    client.request.assert_not_called()
