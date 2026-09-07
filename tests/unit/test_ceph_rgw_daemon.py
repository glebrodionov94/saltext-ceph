"""RGW daemon and site Dashboard adapter tests."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rgw_daemon as execution
from saltext.ceph.utils.ceph import rgw_daemon
from saltext.ceph.utils.ceph import rgw_daemon_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rgw_daemon as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, {})
    return client


def test_wrapper_matches_execution_module():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    assert names
    for name in names:
        assert inspect.signature(getattr(execution, name)) == inspect.signature(
            getattr(wrapper, name)
        )
        api_parameters = list(inspect.signature(getattr(rgw_daemon_api, name)).parameters.values())
        assert inspect.signature(getattr(execution, name)) == inspect.Signature(api_parameters[3:])


def test_list_daemons_uses_public_v1_route(client):
    client.request.return_value = APIResponse(200, [{"id": "rgw.a"}])
    assert rgw_daemon.list_daemons(client).data == [{"id": "rgw.a"}]
    client.request.assert_called_once_with("GET", "/api/rgw/daemon", api_version="1.0")


@pytest.mark.parametrize("payload", [None, {}, ["rgw.a"], [{"id": "a"}, None]])
def test_list_daemons_rejects_malformed_server_data(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        rgw_daemon.list_daemons(client)


def test_get_daemon_encodes_service_id_and_validates_mapping(client):
    client.request.return_value = APIResponse(200, {"rgw_id": "realm/rgw.a"})
    rgw_daemon.get_daemon(client, "realm/rgw.a")
    client.request.assert_called_once_with(
        "GET", "/api/rgw/daemon/realm%2Frgw.a", api_version="1.0"
    )


def test_get_daemon_rejects_invalid_shape(client):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        rgw_daemon.get_daemon(client, "rgw.a")


def test_set_multisite_config_sends_only_supplied_body_fields(client):
    rgw_daemon.set_multisite_config(client, "r1", "zg1", "z1", "rgw.a")
    client.request.assert_called_once_with(
        "PUT",
        "/api/rgw/daemon/set_multisite_config",
        api_version="1.0",
        data={
            "realm_name": "r1",
            "zonegroup_name": "zg1",
            "zone_name": "z1",
            "daemon_name": "rgw.a",
        },
    )


@pytest.mark.parametrize(
    "query",
    ["placement-targets", "realms", "default-realm", "default-zonegroup"],
)
def test_site_supports_only_controller_implemented_queries(client, query):
    rgw_daemon.get_site(client, query, "rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/site",
        api_version="1.0",
        params={"query": query, "daemon_name": "rgw.a"},
    )


def test_site_rejects_unimplemented_query_before_http(client):
    with pytest.raises(ConfigurationError):
        rgw_daemon.get_site(client, "topology")
    client.request.assert_not_called()
