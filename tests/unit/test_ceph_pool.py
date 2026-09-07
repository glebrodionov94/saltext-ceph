"""Pool controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_pool as execution
from saltext.ceph.utils.ceph import pool
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_pool as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(202, {"name": "pool/create"})
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


def test_list_uses_api_v1_and_disables_stats_by_default(client):
    client.request.return_value = APIResponse(
        200, [{"pool_name": "volumes", "type": "replicated", "size": 3}]
    )
    result = pool.list_(client)
    assert result.data[0]["pool_name"] == "volumes"
    client.request.assert_called_once_with(
        "GET", "/api/pool", api_version="1.0", params={"stats": False}
    )


@pytest.mark.parametrize("attrs", [["pool_name", "type", "size"], "pool_name,type,size"])
def test_list_normalizes_selected_attributes(client, attrs):
    client.request.return_value = APIResponse(200, [])
    pool.list_(client, attrs=attrs, stats=True)
    client.request.assert_called_once_with(
        "GET",
        "/api/pool",
        api_version="1.0",
        params={"stats": True, "attrs": "pool_name,type,size"},
    )


@pytest.mark.parametrize(
    "attrs,stats",
    [
        ([], False),
        ("", False),
        (["pool_name", "pool_name"], False),
        (["bad-name"], False),
        ({"pool_name": True}, False),
        (None, "true"),
    ],
)
def test_list_rejects_invalid_query_before_http(client, attrs, stats):
    with pytest.raises(ConfigurationError):
        pool.list_(client, attrs=attrs, stats=stats)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, {}, ["volumes"], [{"pool_name": "volumes"}, None]])
def test_list_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        pool.list_(client)


def test_get_encodes_pool_name_and_passes_query(client):
    client.request.return_value = APIResponse(
        200, {"pool_name": "tenant/data", "configuration": []}
    )
    result = pool.get(client, "tenant/data", attrs=["type"], stats=True)
    assert result.data["pool_name"] == "tenant/data"
    client.request.assert_called_once_with(
        "GET",
        "/api/pool/tenant%2Fdata",
        api_version="1.0",
        params={"stats": True, "attrs": "type"},
    )


def test_get_rejects_non_mapping_response(client):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        pool.get(client, "volumes")


def test_configuration_uses_public_resource_endpoint(client):
    client.request.return_value = APIResponse(
        200, [{"name": "rbd_qos_bps_limit", "source": 2, "value": "1048576"}]
    )
    result = pool.configuration(client, "volumes")
    assert result.data[0]["name"] == "rbd_qos_bps_limit"
    client.request.assert_called_once_with(
        "GET", "/api/pool/volumes/configuration", api_version="1.0"
    )


@pytest.mark.parametrize("payload", [None, {}, ["rbd_qos_bps_limit"], [{}, None]])
def test_configuration_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        pool.configuration(client, "volumes")


def test_create_replicated_pool_sends_explicit_and_extensible_values(client):
    pool.create(
        client,
        "volumes",
        32,
        "REPLICATED",
        application_metadata=["rbd"],
        rule_name="ssd-rule",
        rbd_configuration={"rbd_qos_bps_limit": 1048576},
        options={
            "size": 3,
            "min_size": 2,
            "pg_autoscale_mode": "on",
            "quota_max_bytes": 1073741824,
        },
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/pool",
        api_version="1.0",
        data={
            "pool": "volumes",
            "pg_num": 32,
            "pool_type": "replicated",
            "size": 3,
            "min_size": 2,
            "pg_autoscale_mode": "on",
            "quota_max_bytes": 1073741824,
            "application_metadata": ["rbd"],
            "rule_name": "ssd-rule",
            "configuration": {"rbd_qos_bps_limit": 1048576},
        },
    )


def test_create_erasure_pool_supports_profile_flag_and_current_mirroring(client):
    pool.create(
        client,
        "archive",
        16,
        "erasure",
        erasure_code_profile="ec42",
        flags=["ec_overwrites"],
        application_metadata=["rgw"],
        rbd_mirroring=False,
    )
    assert client.request.call_args.kwargs["data"] == {
        "pool": "archive",
        "pg_num": 16,
        "pool_type": "erasure",
        "erasure_code_profile": "ec42",
        "flags": ["ec_overwrites"],
        "application_metadata": ["rgw"],
        "rbd_mirroring": False,
    }


@pytest.mark.parametrize(
    "args,kwargs",
    [
        (("bad pool", 8, "replicated"), {}),
        (("volumes", True, "replicated"), {}),
        (("volumes", 0, "replicated"), {}),
        (("volumes", "8", "replicated"), {}),
        (("volumes", 8, "mirror"), {}),
        (("volumes", 8, "replicated"), {"erasure_code_profile": "ec42"}),
        (("volumes", 8, "replicated"), {"flags": ["ec_overwrites"]}),
        (("archive", 8, "erasure"), {"flags": ["nodelete"]}),
        (("archive", 8, "erasure"), {"flags": []}),
        (("volumes", 8, "replicated"), {"application_metadata": ["bad/app"]}),
        (("volumes", 8, "replicated"), {"application_metadata": ["rbd", "rbd"]}),
        (("volumes", 8, "replicated"), {"rbd_configuration": []}),
        (("volumes", 8, "replicated"), {"rbd_configuration": {"bad-key": 1}}),
        (("volumes", 8, "replicated"), {"rbd_mirroring": "false"}),
        (("volumes", 8, "replicated"), {"options": []}),
        (("volumes", 8, "replicated"), {"options": {"pool": "other"}}),
        (("volumes", 8, "replicated"), {"options": {"pg_num": 16}}),
        (("volumes", 8, "replicated"), {"options": {"size": [3]}}),
        (("volumes", 8, "replicated"), {"options": {"ratio": float("nan")}}),
        (("volumes", 8, "replicated"), {"options": {"mode": "bad\nvalue"}}),
    ],
)
def test_create_rejects_invalid_payload_before_http(client, args, kwargs):
    with pytest.raises(ConfigurationError):
        pool.create(client, *args, **kwargs)
    client.request.assert_not_called()


def test_update_sends_rename_lists_configuration_mirroring_and_options(client):
    pool.update(
        client,
        "volumes",
        new_name="volumes-v2",
        application_metadata=[],
        rbd_configuration={"rbd_qos_bps_limit": None},
        rbd_mirroring=False,
        options={"pg_num": 64, "size": 3, "compression_mode": "unset"},
    )
    client.request.assert_called_once_with(
        "PUT",
        "/api/pool/volumes",
        api_version="1.0",
        data={
            "pg_num": 64,
            "size": 3,
            "compression_mode": "unset",
            "pool": "volumes-v2",
            "application_metadata": [],
            "configuration": {"rbd_qos_bps_limit": None},
            "rbd_mirroring": False,
        },
    )


def test_update_can_enable_ec_overwrites(client):
    pool.update(client, "archive", flags=["ec_overwrites"])
    assert client.request.call_args.kwargs["data"] == {"flags": ["ec_overwrites"]}


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"new_name": "volumes"},
        {"new_name": "bad name"},
        {"flags": []},
        {"application_metadata": ["bad/app"]},
        {"rbd_configuration": {"bad-key": 1}},
        {"rbd_mirroring": 0},
        {"options": {"flags": "ec_overwrites"}},
        {"options": {"bad-key": 1}},
        {"options": {"size": None}},
    ],
)
def test_update_rejects_invalid_or_empty_payload_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        pool.update(client, "volumes", **kwargs)
    client.request.assert_not_called()


def test_delete_uses_api_v1_and_encodes_pool_name(client):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        pool.delete(client, "tenant/data")
    client.request.assert_not_called()
    pool.delete(client, "tenant/data", confirm=True)
    client.request.assert_called_once_with("DELETE", "/api/pool/tenant%2Fdata", api_version="1.0")


@pytest.mark.parametrize("operation", ["get", "configuration", "delete"])
@pytest.mark.parametrize(
    "pool_name", ["", "/leading", "trailing/", "bad//name", "a/../b", "bad name", 42]
)
def test_resource_operations_validate_pool_name_before_http(client, operation, pool_name):
    with pytest.raises(ConfigurationError):
        getattr(pool, operation)(client, pool_name)
    client.request.assert_not_called()
