"""Current-main RBD group API contracts and salt-ssh parity."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rbd_group as execution
from saltext.ceph.utils.ceph import rbd_group
from saltext.ceph.utils.ceph import rbd_group_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rbd_group as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(202, {"name": "rbd/group/task"})
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


def test_group_list_and_get_use_namespace_query(client):
    client.request.return_value = APIResponse(200, [{"group": "consistency", "num_images": 2}])
    assert rbd_group.list_(client, "rbd", "tenant").data[0]["num_images"] == 2
    client.request.assert_called_once_with(
        "GET",
        "/api/block/pool/rbd/group",
        api_version="1.0",
        params={"namespace": "tenant"},
    )
    client.reset_mock()
    client.request.return_value = APIResponse(200, [{"images": [{"name": "vm-1"}]}])
    rbd_group.get(client, "rbd", "consistency")
    client.request.assert_called_once_with(
        "GET",
        "/api/block/pool/rbd/group/consistency",
        api_version="1.0",
        params={},
    )


def test_group_create_and_update_match_main_controller(client):
    rbd_group.create(client, "rbd", "consistency", namespace="tenant")
    client.request.assert_called_once_with(
        "POST",
        "/api/block/pool/rbd/group",
        api_version="1.0",
        data={"name": "consistency", "namespace": "tenant"},
    )
    client.reset_mock()
    rbd_group.update(client, "rbd", "consistency", "database", namespace="tenant")
    assert client.request.call_args.kwargs["data"] == {
        "new_name": "database",
        "namespace": "tenant",
    }


def test_add_and_remove_image_use_body_and_query_respectively(client):
    rbd_group.add_image(client, "rbd", "consistency", "vm-1", "tenant")
    client.request.assert_called_once_with(
        "POST",
        "/api/block/pool/rbd/group/consistency/image",
        api_version="1.0",
        data={"image_name": "vm-1", "namespace": "tenant"},
    )
    client.reset_mock()
    rbd_group.remove_image(client, "rbd", "consistency", "vm-1", "tenant", confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        "/api/block/pool/rbd/group/consistency/image",
        api_version="1.0",
        params={"image_name": "vm-1", "namespace": "tenant"},
    )


def test_snapshot_collection_and_member_routes(client):
    client.request.return_value = APIResponse(200, [{"name": "daily", "state": "complete"}])
    rbd_group.snapshot_list(client, "rbd", "consistency", "tenant")
    assert client.request.call_args.args[1] == "/api/block/pool/rbd/group/consistency/snap"
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"name": "daily"})
    rbd_group.snapshot_get(client, "rbd", "consistency", "daily")
    assert client.request.call_args.args[1].endswith("/snap/daily")


def test_snapshot_create_and_update_send_flags_and_controller_names(client):
    rbd_group.snapshot_create(client, "rbd", "consistency", "daily", namespace="tenant", flags=1)
    assert client.request.call_args.kwargs["data"] == {
        "snapshot_name": "daily",
        "flags": 1,
        "namespace": "tenant",
    }
    client.reset_mock()
    rbd_group.snapshot_update(client, "rbd", "consistency", "daily", "weekly", namespace="tenant")
    assert client.request.call_args.kwargs["data"] == {
        "new_snap_name": "weekly",
        "namespace": "tenant",
    }


@pytest.mark.parametrize(
    "function,args",
    [
        (rbd_group.delete, ("rbd", "consistency")),
        (rbd_group.remove_image, ("rbd", "consistency", "vm-1")),
        (rbd_group.snapshot_delete, ("rbd", "consistency", "daily")),
        (rbd_group.snapshot_rollback, ("rbd", "consistency", "daily")),
    ],
)
def test_destructive_group_operations_require_confirmation(client, function, args):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        function(client, *args)
    client.request.assert_not_called()
    function(client, *args, confirm=True)


def test_snapshot_rollback_sends_namespace_in_post_body(client):
    rbd_group.snapshot_rollback(
        client, "rbd", "consistency", "daily", namespace="tenant", confirm=True
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/block/pool/rbd/group/consistency/snap/daily/rollback",
        api_version="1.0",
        data={"namespace": "tenant"},
    )


@pytest.mark.parametrize(
    "function,args",
    [
        (rbd_group.list_, ("bad pool",)),
        (rbd_group.get, ("rbd", "bad/group")),
        (rbd_group.create, ("rbd", "bad group")),
        (rbd_group.snapshot_create, ("rbd", "group", "snapshot", None, -1)),
        (rbd_group.snapshot_update, ("rbd", "group", "daily", "daily")),
    ],
)
def test_invalid_group_inputs_fail_before_http(client, function, args):
    with pytest.raises(ConfigurationError):
        function(client, *args)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, {}, ["group"], [{"group": "good"}, None]])
def test_group_list_rejects_invalid_protocol_shape(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        rbd_group.list_(client, "rbd")


def test_api_rejects_unknown_operation():
    with pytest.raises(ConfigurationError, match="Unknown RBD group operation"):
        rbd_group_api.call({}, {}, {}, "missing")
