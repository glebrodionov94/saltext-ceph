"""OSD state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_osd as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def item(device_class="hdd"):
    return {"id": 1, "tree": {"device_class": device_class}, "state": ["up", "in"]}


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_device_class_is_idempotent(monkeypatch):
    set_class = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.set_device_class": set_class,
        },
    )
    assert state.device_class_managed(1, "hdd")["result"] is True
    set_class.assert_not_called()


def test_device_class_changes_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([item()]), envelope([item("ssd")])])
    set_class = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.list": list_, "ceph_osd.set_device_class": set_class},
    )
    result = state.device_class_managed(1, "ssd")
    assert result["result"] is True
    set_class.assert_called_once_with(1, "ssd", profile="default")


def test_cluster_flags_preserve_non_removable_current_flags(monkeypatch):
    flags = Mock(
        side_effect=[envelope(["sortbitwise", "noout"]), envelope(["sortbitwise", "noup"])]
    )
    set_flags = Mock(return_value=envelope(status=200, data=["sortbitwise", "noup"]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.flags": flags, "ceph_osd.set_flags": set_flags},
    )
    result = state.flags_managed("cluster", ["noup"])
    assert result["result"] is True
    set_flags.assert_called_once_with(["noup", "sortbitwise"], profile="default")


def test_cluster_flags_plan_never_mutates(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    set_flags = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.flags": Mock(return_value=envelope([])), "ceph_osd.set_flags": set_flags},
    )
    assert state.flags_managed("cluster", ["noout"])["result"] is None
    set_flags.assert_not_called()


def test_cluster_flags_reject_impossible_purged_snapshots(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.flags": Mock(return_value=envelope([]))},
    )
    result = state.flags_managed("cluster", ["purged_snapshots"])
    assert result["result"] is False


def test_individual_flags_are_idempotent(monkeypatch):
    set_flags = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.individual_flags": Mock(
                return_value=envelope([{"osd": 1, "flags": ["up", "noout"]}])
            ),
            "ceph_osd.set_individual_flags": set_flags,
        },
    )
    assert state.individual_flags_managed("maintenance", [1], {"noout": True})["result"] is True
    set_flags.assert_not_called()


def test_individual_flags_change_and_verify(monkeypatch):
    read = Mock(
        side_effect=[
            envelope([{"osd": 1, "flags": ["up"]}]),
            envelope([{"osd": 1, "flags": ["up", "noout"]}]),
        ]
    )
    set_flags = Mock(return_value=envelope(status=200, data={}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.individual_flags": read, "ceph_osd.set_individual_flags": set_flags},
    )
    result = state.individual_flags_managed("maintenance", [1], {"noout": True})
    assert result["result"] is True
    set_flags.assert_called_once_with({"noout": True}, [1], profile="default")


def test_absent_checks_safety_then_removes(monkeypatch):
    list_ = Mock(side_effect=[envelope([item()]), envelope([])])
    remove = Mock(return_value=envelope({"name": "osd/delete", "metadata": {"svc_id": "1"}}, 202))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": list_,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": remove,
            "ceph_task.wait": wait,
        },
    )
    result = state.absent(1, confirm=True)
    assert result["result"] is True
    remove.assert_called_once_with(
        1, preserve_id=False, force=False, confirm=True, profile="default"
    )
    wait.assert_called_once()


def test_absent_refuses_unsafe_osd(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": False})),
            "ceph_osd.remove": remove,
        },
    )
    result = state.absent(1, confirm=True)
    assert result["result"] is False
    remove.assert_not_called()


def test_absent_force_skips_preflight_but_requires_confirmation(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.list": Mock(return_value=envelope([item()])), "ceph_osd.remove": remove},
    )
    assert state.absent(1, force=True)["result"] is False
    remove.assert_not_called()


def test_absent_test_mode_plans_without_safety_or_confirmation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    safety = Mock()
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.safe_to_delete": safety,
            "ceph_osd.remove": remove,
        },
    )
    assert state.absent(1)["result"] is None
    safety.assert_not_called()
    remove.assert_not_called()


def test_absent_is_idempotent(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.list": Mock(return_value=envelope([])), "ceph_osd.remove": remove},
    )
    assert state.absent(1)["result"] is True
    remove.assert_not_called()
