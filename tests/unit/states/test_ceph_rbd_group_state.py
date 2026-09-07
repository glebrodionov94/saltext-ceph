"""Declarative current-Ceph RBD group states."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_rbd_group as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def task():
    return envelope(
        {"name": "rbd/group", "metadata": {"pool_name": "rbd", "group": "db"}},
        202,
    )


def groups(count=2):
    return envelope([{"group": "db", "num_images": count}])


def members(*names):
    return envelope([{"images": [{"name": name, "pool": 1, "state": 0} for name in names]}])


def snapshots(*names):
    return envelope([{"name": name, "id": name + "-id", "state": "complete"} for name in names])


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_virtual_requires_complete_execution_surface(monkeypatch):
    monkeypatch.setattr(state, "__salt__", {"ceph_rbd_group.list": Mock()})
    result = state.__virtual__()
    assert result[0] is False
    assert "ceph_rbd_group.snapshot_create" in result[1]


def test_present_can_manage_existence_only_without_detail_read(monkeypatch):
    get = Mock()
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups(1)),
            "ceph_rbd_group.get": get,
            "ceph_rbd_group.create": create,
        },
    )
    result = state.present("db", "rbd", namespace="tenant")
    assert result["result"] is True
    assert not result["changes"]
    get.assert_not_called()
    create.assert_not_called()


def test_present_exact_membership_is_order_independent(monkeypatch):
    add = Mock()
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups()),
            "ceph_rbd_group.get": Mock(return_value=members("vm-b", "vm-a")),
            "ceph_rbd_group.add_image": add,
            "ceph_rbd_group.remove_image": remove,
        },
    )
    result = state.present("db", "rbd", images=["vm-a", "vm-b"])
    assert result["result"] is True
    assert not result["changes"]
    add.assert_not_called()
    remove.assert_not_called()


def test_present_test_mode_reports_complete_projection_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    add = Mock()
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups(1)),
            "ceph_rbd_group.get": Mock(return_value=members("old")),
            "ceph_rbd_group.add_image": add,
            "ceph_rbd_group.remove_image": remove,
        },
    )
    result = state.present("db", "rbd", images=["new"])
    assert result["result"] is None
    assert result["changes"]["old"]["images"] == ["old"]
    assert result["changes"]["new"]["images"] == ["new"]
    add.assert_not_called()
    remove.assert_not_called()


def test_present_requires_confirmation_before_any_membership_removal(monkeypatch):
    add = Mock()
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups()),
            "ceph_rbd_group.get": Mock(return_value=members("old", "keep")),
            "ceph_rbd_group.add_image": add,
            "ceph_rbd_group.remove_image": remove,
        },
    )
    result = state.present("db", "rbd", images=["keep", "new"])
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    add.assert_not_called()
    remove.assert_not_called()


def test_present_creates_adds_members_waits_and_post_reads(monkeypatch):
    list_ = Mock(side_effect=[envelope([]), groups(0), groups(2)])
    get = Mock(return_value=members("vm-a", "vm-b"))
    create = Mock(return_value=task())
    add = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": list_,
            "ceph_rbd_group.get": get,
            "ceph_rbd_group.create": create,
            "ceph_rbd_group.add_image": add,
            "ceph_rbd_group.remove_image": Mock(),
            "ceph_task.wait": wait,
        },
    )
    result = state.present("db", "rbd", images=["vm-b", "vm-a"])
    assert result["result"] is True
    assert [call.args[2] for call in add.call_args_list] == ["vm-a", "vm-b"]
    assert wait.call_count == 3
    assert result["changes"]["old"] is None


def test_present_reconciles_additions_and_removals_then_verifies(monkeypatch):
    list_ = Mock(side_effect=[groups(2), groups(2)])
    get = Mock(side_effect=[members("keep", "old"), members("keep", "old"), members("keep", "new")])
    add = Mock(return_value=envelope(status=200))
    remove = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": list_,
            "ceph_rbd_group.get": get,
            "ceph_rbd_group.add_image": add,
            "ceph_rbd_group.remove_image": remove,
        },
    )
    result = state.present("db", "rbd", images=["keep", "new"], confirm=True)
    assert result["result"] is True
    add.assert_called_once_with("rbd", "db", "new", namespace=None, profile="default")
    remove.assert_called_once_with(
        "rbd", "db", "old", namespace=None, confirm=True, profile="default"
    )


def test_absent_removes_members_then_group_and_post_reads(monkeypatch):
    list_ = Mock(side_effect=[groups(2), envelope([])])
    remove = Mock(return_value=task())
    delete = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": list_,
            "ceph_rbd_group.get": Mock(return_value=members("vm-a", "vm-b")),
            "ceph_rbd_group.remove_image": remove,
            "ceph_rbd_group.delete": delete,
            "ceph_task.wait": wait,
        },
    )
    result = state.absent("db", "rbd", confirm=True)
    assert result["result"] is True
    assert [call.args[2] for call in remove.call_args_list] == ["vm-a", "vm-b"]
    delete.assert_called_once_with("rbd", "db", namespace=None, confirm=True, profile="default")
    assert wait.call_count == 3


def test_absent_test_mode_does_not_require_confirmation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups(0)),
            "ceph_rbd_group.get": Mock(return_value=members()),
            "ceph_rbd_group.delete": delete,
        },
    )
    assert state.absent("db", "rbd")["result"] is None
    delete.assert_not_called()


def test_snapshot_present_is_idempotent(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups()),
            "ceph_rbd_group.snapshot_list": Mock(return_value=snapshots("daily")),
            "ceph_rbd_group.snapshot_create": create,
        },
    )
    result = state.snapshot_present("daily", "rbd", "db")
    assert result["result"] is True
    create.assert_not_called()


def test_snapshot_present_waits_and_post_reads(monkeypatch):
    create = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups()),
            "ceph_rbd_group.snapshot_list": Mock(side_effect=[snapshots(), snapshots("daily")]),
            "ceph_rbd_group.snapshot_create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.snapshot_present("daily", "rbd", "db", namespace="tenant")
    assert result["result"] is True
    create.assert_called_once_with(
        "rbd", "db", "daily", namespace="tenant", flags=0, profile="default"
    )
    wait.assert_called_once()


def test_snapshot_present_requires_parent_group(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=envelope([])),
            "ceph_rbd_group.snapshot_create": create,
        },
    )
    result = state.snapshot_present("daily", "rbd", "db")
    assert result["result"] is False
    assert "does not exist" in result["comment"]
    create.assert_not_called()


def test_snapshot_absent_requires_confirmation_and_verifies(monkeypatch):
    delete = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    snap_list = Mock(side_effect=[snapshots("daily"), snapshots()])
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups()),
            "ceph_rbd_group.snapshot_list": snap_list,
            "ceph_rbd_group.snapshot_delete": delete,
            "ceph_task.wait": wait,
        },
    )
    assert state.snapshot_absent("daily", "rbd", "db")["result"] is False
    delete.assert_not_called()
    snap_list.side_effect = [snapshots("daily"), snapshots()]
    result = state.snapshot_absent("daily", "rbd", "db", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with(
        "rbd", "db", "daily", namespace=None, confirm=True, profile="default"
    )
    wait.assert_called_once()


@pytest.mark.parametrize("images", [["vm", "vm"], "vm", ["bad/name"]])
def test_invalid_membership_fails_before_api(monkeypatch, images):
    list_ = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_rbd_group.list": list_})
    result = state.present("db", "rbd", images=images)
    assert result["result"] is False
    list_.assert_not_called()


def test_malformed_group_detail_fails_without_mutation(monkeypatch):
    add = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_group.list": Mock(return_value=groups(1)),
            "ceph_rbd_group.get": Mock(return_value=envelope([{"images": [None]}])),
            "ceph_rbd_group.add_image": add,
        },
    )
    result = state.present("db", "rbd", images=["vm"])
    assert result["result"] is False
    assert "invalid image membership" in result["comment"]
    add.assert_not_called()
