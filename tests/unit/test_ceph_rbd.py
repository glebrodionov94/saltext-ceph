"""RBD image API contracts, validation, tasks, and salt-ssh parity."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rbd as execution
from saltext.ceph.utils.ceph import rbd
from saltext.ceph.utils.ceph import rbd_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rbd as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(202, {"name": "rbd/task"})
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


def test_list_uses_v2_pagination_namespace_and_preserves_total(client):
    client.request.return_value = APIResponse(
        200,
        [{"pool_name": "rbd", "value": [{"name": "vm-1", "namespace": "tenant"}]}],
        {"x-total-count": "1"},
    )
    result = rbd.list_(
        client,
        pool_name="rbd",
        namespace="tenant",
        offset=5,
        limit=10,
        search="vm",
        sort="-name",
    )
    assert result.headers == {"x-total-count": "1"}
    assert result.data[0]["value"][0]["name"] == "vm-1"
    client.request.assert_called_once_with(
        "GET",
        "/api/block/image",
        api_version="2.0",
        params={
            "offset": 5,
            "limit": 10,
            "search": "vm",
            "sort": "-name",
            "pool_name": "rbd",
            "namespace": "tenant",
        },
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"offset": -1},
        {"offset": True},
        {"limit": 0},
        {"limit": -2},
        {"sort": "name"},
        {"sort": "+size"},
        {"search": "bad\nvalue"},
        {"namespace": "bad/name"},
    ],
)
def test_list_rejects_invalid_queries_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        rbd.list_(client, **kwargs)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [None, {}, ["bad"], [{"pool_name": "rbd"}], [{"pool_name": "rbd", "value": [None]}]],
)
def test_list_rejects_invalid_protocol_shapes(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        rbd.list_(client)


def test_image_spec_builder_and_get_encoding_are_namespace_aware(client):
    assert rbd.make_image_spec("rbd", "vm-1") == "rbd/vm-1"
    assert rbd.make_image_spec("rbd", "vm-1", "tenant") == "rbd/tenant/vm-1"
    client.request.return_value = APIResponse(200, {"name": "vm-1"})
    rbd.get(client, "rbd/tenant/vm-1", omit_usage=True)
    client.request.assert_called_once_with(
        "GET",
        "/api/block/image/rbd%2Ftenant%2Fvm-1",
        api_version="1.0",
        params={"omit_usage": True},
    )


def test_get_omits_main_only_query_by_default_for_reef(client):
    client.request.return_value = APIResponse(200, {"name": "vm-1"})
    rbd.get(client, "rbd/vm-1")
    client.request.assert_called_once_with("GET", "/api/block/image/rbd%2Fvm-1", api_version="1.0")


@pytest.mark.parametrize("image_spec", ["", "rbd", "/image", "rbd/", "rbd//image", "a/b/c/d", 1])
def test_member_operations_reject_invalid_image_specs(client, image_spec):
    with pytest.raises(ConfigurationError):
        rbd.get(client, image_spec)
    client.request.assert_not_called()


def test_create_sends_complete_controller_payload(client):
    result = rbd.create(
        client,
        "vm-1",
        "rbd",
        1 << 30,
        namespace="tenant",
        schedule_interval="6h",
        obj_size=1 << 22,
        features=["layering", "exclusive-lock"],
        stripe_unit=1 << 22,
        stripe_count=4,
        data_pool="rbd-data",
        configuration={"rbd_qos_bps_limit": 1048576},
        metadata={"owner": "compute"},
        mirror_mode="snapshot",
    )
    assert result.status == 202
    client.request.assert_called_once_with(
        "POST",
        "/api/block/image",
        api_version="1.0",
        data={
            "name": "vm-1",
            "pool_name": "rbd",
            "size": 1 << 30,
            "namespace": "tenant",
            "obj_size": 1 << 22,
            "stripe_unit": 1 << 22,
            "stripe_count": 4,
            "data_pool": "rbd-data",
            "features": ["layering", "exclusive-lock"],
            "configuration": {"rbd_qos_bps_limit": 1048576},
            "metadata": {"owner": "compute"},
            "mirror_mode": "snapshot",
            "schedule_interval": "6h",
        },
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"size": 0},
        {"obj_size": 3},
        {"features": ["unknown"]},
        {"features": ["layering", "layering"]},
        {"configuration": []},
        {"configuration": {"bad-name": 1}},
        {"metadata": {"owner": []}},
        {"metadata": {"owner": 42}},
        {"mirror_mode": "pool"},
        {"schedule_interval": "5s", "mirror_mode": "snapshot"},
        {"schedule_interval": "1h", "mirror_mode": "journal"},
    ],
)
def test_create_rejects_invalid_payloads_before_http(client, kwargs):
    arguments = {"name": "vm-1", "pool_name": "rbd", "size": 1024}
    arguments.update(kwargs)
    with pytest.raises(ConfigurationError):
        rbd.create(client, **arguments)
    client.request.assert_not_called()


def test_update_keeps_reef_compatible_payload_minimal(client):
    rbd.update(client, "rbd/vm-1", name="vm-2")
    client.request.assert_called_once_with(
        "PUT",
        "/api/block/image/rbd%2Fvm-1",
        api_version="1.0",
        data={"name": "vm-2"},
    )


def test_update_supports_current_main_mirroring_schedule_fields(client):
    rbd.update(
        client,
        "rbd/tenant/vm-1",
        enable_mirror=True,
        mirror_mode="snapshot",
        image_mirror_mode="journal",
        schedule_interval="15m",
        schedule_level="pool",
        confirm=True,
    )
    assert client.request.call_args.kwargs["data"] == {
        "enable_mirror": True,
        "mirror_mode": "snapshot",
        "image_mirror_mode": "journal",
        "schedule_interval": "15m",
        "schedule_level": "pool",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"enable_mirror": True},
        {"force": True, "confirm": True},
        {"image_mirror_mode": "journal"},
        {"schedule_level": "pool"},
        {"schedule_interval": "0h"},
        {"remove_scheduling": "yes", "confirm": True},
    ],
)
def test_update_rejects_invalid_or_empty_actions(client, kwargs):
    with pytest.raises(ConfigurationError):
        rbd.update(client, "rbd/vm-1", **kwargs)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [{"size": 2048}, {"enable_mirror": False}, {"primary": False}, {"resync": True}],
)
def test_update_requires_confirmation_for_risky_changes(client, kwargs):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        rbd.update(client, "rbd/vm-1", **kwargs)
    kwargs["confirm"] = True
    rbd.update(client, "rbd/vm-1", **kwargs)


def test_copy_and_snapshot_clone_use_controller_names(client):
    rbd.copy(client, "rbd/vm-1", "backup", None, "vm-copy", snapshot_name="daily")
    assert client.request.call_args.kwargs["data"] == {
        "dest_pool_name": "backup",
        "dest_namespace": "",
        "dest_image_name": "vm-copy",
        "snapshot_name": "daily",
    }
    client.reset_mock()
    rbd.snapshot_clone(
        client,
        "rbd/vm-1",
        "42",
        "backup",
        "vm-clone",
        clone_by_snap_id=True,
    )
    assert client.request.call_args.args[1].endswith("/snap/42/clone")
    assert client.request.call_args.kwargs["data"]["clone_by_snap_id"] is True


def test_snapshot_clone_by_id_rejects_a_snapshot_name(client):
    with pytest.raises(ConfigurationError, match="decimal ID"):
        rbd.snapshot_clone(
            client,
            "rbd/vm-1",
            "daily",
            "backup",
            "vm-clone",
            clone_by_snap_id=True,
        )
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "function,args",
    [
        (rbd.delete, ("rbd/vm-1",)),
        (rbd.flatten, ("rbd/vm-1",)),
        (rbd.move_to_trash, ("rbd/vm-1",)),
        (rbd.trash_purge, ("rbd",)),
        (rbd.trash_delete, ("rbd/deadbeef",)),
        (rbd.namespace_delete, ("rbd", "tenant")),
        (rbd.snapshot_delete, ("rbd/vm-1", "daily")),
        (rbd.snapshot_rollback, ("rbd/vm-1", "daily")),
    ],
)
def test_destructive_operations_require_exact_confirmation(client, function, args):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        function(client, *args)
    function(client, *args, confirm=True)


def test_trash_routes_and_force_query_match_openapi(client):
    rbd.trash_restore(client, "rbd/tenant/deadbeef", "vm-restored")
    client.request.assert_called_once_with(
        "POST",
        "/api/block/image/trash/rbd%2Ftenant%2Fdeadbeef/restore",
        api_version="1.0",
        data={"new_image_name": "vm-restored"},
    )
    client.reset_mock()
    rbd.trash_delete(client, "rbd/deadbeef", force=True, confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        "/api/block/image/trash/rbd%2Fdeadbeef",
        api_version="1.0",
        params={"force": True},
    )


def test_namespace_resource_routes_encode_segments(client):
    rbd.namespace_create(client, "rbd", "tenant")
    client.request.assert_called_once_with(
        "POST",
        "/api/block/pool/rbd/namespace",
        api_version="1.0",
        data={"namespace": "tenant"},
    )
    client.reset_mock()
    rbd.namespace_delete(client, "rbd", "tenant", confirm=True)
    assert client.request.call_args.args == (
        "DELETE",
        "/api/block/pool/rbd/namespace/tenant",
    )


def test_snapshot_create_update_and_rollback_match_openapi(client):
    rbd.snapshot_create(client, "rbd/vm-1", "daily", mirror_image_snapshot=True)
    assert client.request.call_args.kwargs["data"] == {
        "snapshot_name": "daily",
        "mirrorImageSnapshot": True,
    }
    client.reset_mock()
    rbd.snapshot_update(client, "rbd/vm-1", "daily", new_snapshot_name="weekly", is_protected=True)
    assert client.request.call_args.kwargs["data"] == {
        "new_snap_name": "weekly",
        "is_protected": True,
    }
    client.reset_mock()
    rbd.snapshot_rollback(client, "rbd/vm-1", "weekly", confirm=True)
    assert client.request.call_args.args[1].endswith("/snap/weekly/rollback")


def test_default_features_and_clone_format_validate_responses(client):
    client.request.return_value = APIResponse(200, ["layering", "exclusive-lock"])
    assert rbd.default_features(client).data == ["layering", "exclusive-lock"]
    client.request.return_value = APIResponse(200, 2)
    assert rbd.clone_format_version(client).data == 2
    client.request.return_value = APIResponse(200, True)
    with pytest.raises(ProtocolError):
        rbd.clone_format_version(client)


def test_api_rejects_unknown_operation():
    with pytest.raises(ConfigurationError, match="Unknown RBD operation"):
        rbd_api.call({}, {}, {}, "missing")
