"""Cluster configuration controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_cluster_config as execution
from saltext.ceph.utils.ceph import cluster_configuration
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_cluster_config as wrapper


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


def test_list_returns_copied_option_mappings(client):
    source = [{"name": "debug_ms", "value": [{"section": "mon", "value": "0/3"}]}]
    client.request.return_value = APIResponse(200, source)
    result = cluster_configuration.list_(client)
    assert result.data == source
    assert result.data is not source
    client.request.assert_called_once_with("GET", "/api/cluster_conf", api_version="1.0")


@pytest.mark.parametrize("payload", [None, {}, ["debug_ms"], [{"name": "debug_ms"}, None]])
def test_list_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        cluster_configuration.list_(client)


def test_get_quotes_cephadm_option_name(client):
    client.request.return_value = APIResponse(200, {"name": "mgr/cephadm/use_agent"})
    result = cluster_configuration.get(client, "mgr/cephadm/use_agent")
    assert result.data["name"] == "mgr/cephadm/use_agent"
    client.request.assert_called_once_with(
        "GET", "/api/cluster_conf/mgr%2Fcephadm%2Fuse_agent", api_version="1.0"
    )


def test_get_rejects_invalid_response(client):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        cluster_configuration.get(client, "debug_ms")


def test_filter_uses_one_query_value(client):
    client.request.return_value = APIResponse(200, [{"name": "debug_ms"}])
    result = cluster_configuration.filter_(client, ["debug_ms", "mgr/cephadm/use_agent"])
    assert result.data == [{"name": "debug_ms"}]
    client.request.assert_called_once_with(
        "GET",
        "/api/cluster_conf/filter",
        api_version="1.0",
        params={"names": "debug_ms,mgr/cephadm/use_agent"},
    )


@pytest.mark.parametrize("names", [None, [], "debug_ms", ["debug_ms", "debug_ms"]])
def test_filter_rejects_invalid_name_lists_before_http(client, names):
    with pytest.raises(ConfigurationError):
        cluster_configuration.filter_(client, names)
    client.request.assert_not_called()


def test_set_sends_typed_values_and_explicit_removals(client):
    cluster_configuration.set_(
        client,
        "mon_allow_pool_delete",
        [
            {"section": "mon", "value": True},
            {"section": "mon.a", "value": None},
            {"section": "mon.b", "value": ""},
        ],
        force_update=False,
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/cluster_conf",
        api_version="1.0",
        data={
            "name": "mon_allow_pool_delete",
            "value": [
                {"section": "mon", "value": True},
                {"section": "mon.a", "value": None},
                {"section": "mon.b", "value": ""},
            ],
            "force_update": False,
        },
    )


def test_set_omits_unspecified_force_update(client):
    cluster_configuration.set_(client, "debug_ms", [{"section": "global", "value": "0/3"}])
    assert client.request.call_args.kwargs["data"] == {
        "name": "debug_ms",
        "value": [{"section": "global", "value": "0/3"}],
    }


@pytest.mark.parametrize(
    "name,values,force_update",
    [
        ("bad,name", [{"section": "mon", "value": "1"}], None),
        ("debug_ms", [], None),
        ("debug_ms", {"section": "mon", "value": "1"}, None),
        ("debug_ms", [{"section": "mon"}], None),
        ("debug_ms", [{"section": "mon", "value": []}], None),
        ("debug_ms", [{"section": "mon?", "value": "1"}], None),
        (
            "debug_ms",
            [{"section": "mon", "value": "1"}, {"section": "mon", "value": "2"}],
            None,
        ),
        ("debug_ms", [{"section": "mon", "value": "1\n2"}], None),
        ("debug_ms", [{"section": "mon", "value": "1"}], "true"),
    ],
)
def test_set_rejects_invalid_payload_before_http(client, name, values, force_update):
    with pytest.raises(ConfigurationError):
        cluster_configuration.set_(client, name, values, force_update)
    client.request.assert_not_called()


def test_remove_uses_section_query_parameter(client):
    cluster_configuration.remove(client, "debug_ms", "osd/host:storage-1")
    client.request.assert_called_once_with(
        "DELETE",
        "/api/cluster_conf/debug_ms",
        api_version="1.0",
        params={"section": "osd/host:storage-1"},
    )


def test_bulk_set_preserves_scalar_json_types(client):
    cluster_configuration.bulk_set(
        client,
        {
            "osd_max_backfills": {"section": "osd", "value": 1},
            "osd_recovery_sleep": {"section": "osd", "value": 2.0},
        },
    )
    client.request.assert_called_once_with(
        "PUT",
        "/api/cluster_conf",
        api_version="1.0",
        data={
            "options": {
                "osd_max_backfills": {"section": "osd", "value": 1},
                "osd_recovery_sleep": {"section": "osd", "value": 2.0},
            }
        },
    )


@pytest.mark.parametrize(
    "options",
    [
        None,
        {},
        [],
        {"bad,name": {"section": "osd", "value": 1}},
        {"debug_ms": {"section": "osd"}},
        {"debug_ms": {"section": "osd", "value": None}},
        {"debug_ms": {"section": "osd", "value": float("inf")}},
    ],
)
def test_bulk_set_rejects_invalid_payload_before_http(client, options):
    with pytest.raises(ConfigurationError):
        cluster_configuration.bulk_set(client, options)
    client.request.assert_not_called()
