"""Declarative RBD image, namespace, and snapshot states."""

from unittest.mock import Mock

import pytest
from salt.exceptions import CommandExecutionError

from saltext.ceph.states import ceph_rbd as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def task():
    return envelope({"name": "rbd/mutate", "metadata": {"image_spec": "rbd/vm"}}, 202)


def image(**changes):
    value = {
        "name": "vm",
        "pool_name": "rbd",
        "namespace": None,
        "size": 1024,
        "obj_size": 4_194_304,
        "stripe_unit": 4_194_304,
        "stripe_count": 1,
        "data_pool": None,
        "features_name": ["layering", "exclusive-lock"],
        "configuration": [],
        "metadata": {},
        "mirror_mode": "Disabled",
        "snapshots": [],
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_virtual_requires_complete_execution_surface(monkeypatch):
    monkeypatch.setattr(state, "__salt__", {"ceph_rbd.get": Mock()})
    result = state.__virtual__()
    assert result[0] is False
    assert "ceph_rbd.create" in result[1]


def test_image_present_is_idempotent_for_exact_public_projection(monkeypatch):
    get = Mock(return_value=envelope(image()))
    update = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_rbd.get": get, "ceph_rbd.update": update})
    result = state.image_present(
        "rbd/vm",
        1024,
        features=["exclusive-lock", "layering"],
        obj_size=4_194_304,
        stripe_unit=4_194_304,
        stripe_count=1,
        data_pool=None,
        configuration={},
        metadata={},
        mirror_mode="disabled",
    )
    assert result["result"] is True
    assert not result["changes"]
    update.assert_not_called()
    assert get.call_args.kwargs == {"profile": "default"}


def test_image_present_test_mode_plans_create_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd.get": Mock(
                side_effect=CommandExecutionError("missing", info={"status": 404})
            ),
            "ceph_rbd.create": create,
        },
    )
    result = state.image_present("rbd/vm", 1024, features=["layering"])
    assert result["result"] is None
    assert result["changes"]["old"] is None
    assert result["changes"]["new"]["features"] == ["layering"]
    create.assert_not_called()


def test_image_present_creates_waits_and_post_reads(monkeypatch):
    get = Mock(
        side_effect=[
            CommandExecutionError("missing", info={"status": 404}),
            envelope(image(features_name=["layering"])),
        ]
    )
    create = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rbd.get": get, "ceph_rbd.create": create, "ceph_task.wait": wait},
    )
    result = state.image_present("rbd/vm", 1024, features=["layering"])
    assert result["result"] is True
    create.assert_called_once_with(
        "vm",
        "rbd",
        1024,
        namespace=None,
        obj_size=None,
        features=["layering"],
        stripe_unit=None,
        stripe_count=None,
        data_pool=None,
        configuration=None,
        metadata=None,
        mirror_mode=None,
        profile="default",
    )
    wait.assert_called_once()
    assert get.call_count == 2


def test_image_present_sends_only_supported_mutable_drift(monkeypatch):
    before = image(
        configuration=[
            {"name": "rbd_qos_bps_limit", "value": "50", "source": 2},
            {"name": "inherited", "value": "10", "source": 1},
            {"name": "old", "value": "x", "source": "image"},
        ],
        metadata={"owner": "old", "extra": "remove"},
    )
    after = image(
        features_name=["layering", "exclusive-lock", "object-map"],
        configuration=[
            {"name": "rbd_qos_bps_limit", "value": "100", "source": 2},
            {"name": "inherited", "value": "10", "source": 1},
        ],
        metadata={"owner": "new"},
    )
    update = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd.get": Mock(side_effect=[envelope(before), envelope(after)]),
            "ceph_rbd.update": update,
        },
    )
    result = state.image_present(
        "rbd/vm",
        1024,
        features=["layering", "exclusive-lock", "object-map"],
        configuration={"rbd_qos_bps_limit": 100},
        metadata={"owner": "new"},
    )
    assert result["result"] is True
    kwargs = update.call_args.kwargs
    assert kwargs["features"] == ["exclusive-lock", "layering", "object-map"]
    assert kwargs["configuration"] == {"old": None, "rbd_qos_bps_limit": "100"}
    assert kwargs["metadata"] == {"extra": None, "owner": "new"}
    assert kwargs["confirm"] is False


@pytest.mark.parametrize(
    "arguments,match",
    [
        ({"obj_size": 8_388_608}, "create-only"),
        ({"features": ["exclusive-lock"]}, "cannot update"),
    ],
)
def test_image_present_rejects_unreconcilable_existing_drift(monkeypatch, arguments, match):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rbd.get": Mock(return_value=envelope(image())), "ceph_rbd.update": update},
    )
    result = state.image_present("rbd/vm", 1024, **arguments)
    assert result["result"] is False
    assert match in result["comment"]
    update.assert_not_called()


def test_image_resize_requires_confirm_but_test_mode_can_preview(monkeypatch):
    update = Mock()
    salt = {"ceph_rbd.get": Mock(return_value=envelope(image())), "ceph_rbd.update": update}
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.image_present("rbd/vm", 2048)
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    update.assert_not_called()
    monkeypatch.setattr(state, "__opts__", {"test": True})
    assert state.image_present("rbd/vm", 2048)["result"] is None


def test_image_absent_requires_confirmation_and_verifies_deletion(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    get = Mock(return_value=envelope(image()))
    monkeypatch.setattr(state, "__salt__", {"ceph_rbd.get": get, "ceph_rbd.delete": delete})
    assert state.image_absent("rbd/vm")["result"] is False
    delete.assert_not_called()
    get.side_effect = [
        envelope(image()),
        CommandExecutionError("missing", info={"status": 404}),
    ]
    result = state.image_absent("rbd/vm", confirm=True)
    assert result["result"] is True
    assert result["changes"]["new"] is None


def test_credential_like_metadata_is_rejected_before_read_and_not_echoed(monkeypatch):
    get = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_rbd.get": get})
    result = state.image_present("rbd/vm", 1024, metadata={"access_token": "do-not-print"})
    assert result["result"] is False
    assert "do-not-print" not in result["comment"]
    assert not result["changes"]
    get.assert_not_called()


def test_namespace_present_creates_waits_and_verifies(monkeypatch):
    list_ = Mock(
        side_effect=[
            envelope([]),
            envelope([{"namespace": "tenant", "num_images": 0}]),
        ]
    )
    create = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd.namespace_list": list_,
            "ceph_rbd.namespace_create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.namespace_present("tenant", "rbd")
    assert result["result"] is True
    create.assert_called_once_with("rbd", "tenant", profile="default")
    wait.assert_called_once()


def test_namespace_delete_requires_empty_and_confirm(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd.namespace_list": Mock(
                return_value=envelope([{"namespace": "tenant", "num_images": 1}])
            ),
            "ceph_rbd.namespace_delete": delete,
        },
    )
    result = state.namespace_absent("tenant", "rbd", confirm=True)
    assert result["result"] is False
    assert "empty" in result["comment"]
    delete.assert_not_called()


def test_namespace_delete_test_mode_does_not_require_confirmation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd.namespace_list": Mock(
                return_value=envelope([{"namespace": "tenant", "num_images": 0}])
            ),
            "ceph_rbd.namespace_delete": delete,
        },
    )
    assert state.namespace_absent("tenant", "rbd")["result"] is None
    delete.assert_not_called()


def test_snapshot_present_creates_protects_waits_and_preserves_old_none(monkeypatch):
    unprotected = {"name": "daily", "is_protected": False}
    protected = {"name": "daily", "is_protected": True}
    get = Mock(
        side_effect=[
            envelope(image()),
            envelope(image(snapshots=[unprotected])),
            envelope(image(snapshots=[protected])),
        ]
    )
    create = Mock(return_value=task())
    update = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd.get": get,
            "ceph_rbd.snapshot_create": create,
            "ceph_rbd.snapshot_update": update,
            "ceph_task.wait": wait,
        },
    )
    result = state.snapshot_present("daily", "rbd/vm", is_protected=True)
    assert result["result"] is True
    assert result["changes"]["old"] is None
    assert result["changes"]["new"] == {"name": "daily", "is_protected": True}
    assert wait.call_count == 2


def test_snapshot_present_rejects_mirroring_snapshot_protection(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd.get": Mock(
                return_value=envelope(image(snapshots=[{"name": "mirror", "is_protected": None}]))
            )
        },
    )
    result = state.snapshot_present("mirror", "rbd/vm", is_protected=True)
    assert result["result"] is False
    assert "Mirroring snapshots" in result["comment"]


def test_snapshot_absent_confirmation_and_post_read(monkeypatch):
    present = image(snapshots=[{"name": "daily", "is_protected": False}])
    delete = Mock(return_value=envelope(status=204))
    get = Mock(side_effect=[envelope(present), envelope(image())])
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rbd.get": get, "ceph_rbd.snapshot_delete": delete},
    )
    result = state.snapshot_absent("daily", "rbd/vm", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with("rbd/vm", "daily", confirm=True, profile="default")


def test_malformed_image_response_fails_without_mutation(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd.get": Mock(return_value=envelope({"name": "other"})),
            "ceph_rbd.update": update,
        },
    )
    result = state.image_present("rbd/vm", 1024)
    assert result["result"] is False
    assert "did not match" in result["comment"]
    update.assert_not_called()
