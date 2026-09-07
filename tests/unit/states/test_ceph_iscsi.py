"""Declarative iSCSI target state tests."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_iscsi as state

IQN = "iqn.2024-01.com.example:target"


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def target(**changes):
    value = {
        "target_iqn": IQN,
        "target_controls": {},
        "acl_enabled": False,
        "auth": {"user": "", "password": "", "mutual_user": "", "mutual_password": ""},
        "portals": [{"host": "node1", "ip": "192.0.2.10"}],
        "disks": [],
        "clients": [],
        "groups": [],
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_present_is_idempotent(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": Mock(return_value=envelope([{"target_iqn": IQN}])),
            "ceph_iscsi.get_target": Mock(return_value=envelope(target(extra=True))),
            "ceph_iscsi.create_target": create,
        },
    )
    result = state.present(IQN, [{"host": "node1", "ip": "192.0.2.10"}])
    assert result["result"] is True
    create.assert_not_called()


def test_present_plans_create_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": Mock(return_value=envelope([])),
            "ceph_iscsi.create_target": create,
        },
    )
    result = state.present(IQN, [{"host": "node1", "ip": "192.0.2.10"}])
    assert result["result"] is None
    create.assert_not_called()


def test_present_creates_waits_and_verifies(monkeypatch):
    lists = Mock(side_effect=[envelope([]), envelope([{"target_iqn": IQN}])])
    create = Mock(
        return_value=envelope({"name": "iscsi/target/create", "metadata": {"target_iqn": IQN}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": lists,
            "ceph_iscsi.get_target": Mock(return_value=envelope(target())),
            "ceph_iscsi.create_target": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.present(IQN, [{"host": "node1", "ip": "192.0.2.10"}])
    assert result["result"] is True
    create.assert_called_once()
    wait.assert_called_once()


def test_present_requires_confirmation_for_drift(monkeypatch):
    update = Mock()
    before = target(acl_enabled=True)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": Mock(return_value=envelope([{"target_iqn": IQN}])),
            "ceph_iscsi.get_target": Mock(return_value=envelope(before)),
            "ceph_iscsi.update_target": update,
        },
    )
    result = state.present(IQN, [{"host": "node1", "ip": "192.0.2.10"}])
    assert result["result"] is False
    assert "confirm_update=True" in result["comment"]
    update.assert_not_called()


def test_present_updates_and_redacts_changes(monkeypatch):
    auth = {
        "user": "chapuser1",
        "password": "privatepass1",
        "mutual_user": "",
        "mutual_password": "",
    }
    before = target()
    after = target(auth=auth)
    lists = Mock(
        side_effect=[
            envelope([{"target_iqn": IQN}]),
            envelope([{"target_iqn": IQN}]),
        ]
    )
    get = Mock(side_effect=[envelope(before), envelope(after)])
    update = Mock(return_value=envelope({}, 200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": lists,
            "ceph_iscsi.get_target": get,
            "ceph_iscsi.update_target": update,
        },
    )
    result = state.present(
        IQN,
        [{"host": "node1", "ip": "192.0.2.10"}],
        auth=auth,
        confirm_update=True,
    )
    assert result["result"] is True
    assert "privatepass1" not in repr(result)
    assert result["changes"]["new"]["auth"]["password"] == "***********"
    assert update.call_args.kwargs["confirm"] is True


def test_test_mode_plans_drift_without_confirmation_and_redacts(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    current = target(
        auth={
            "user": "chapuser1",
            "password": "oldprivate12",
            "mutual_user": "",
            "mutual_password": "",
        }
    )
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": Mock(return_value=envelope([{"target_iqn": IQN}])),
            "ceph_iscsi.get_target": Mock(return_value=envelope(current)),
        },
    )
    result = state.present(IQN, [{"host": "node1", "ip": "192.0.2.10"}])
    assert result["result"] is None
    assert "oldprivate12" not in repr(result)


def test_absent_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": Mock(return_value=envelope([])),
            "ceph_iscsi.delete_target": delete,
        },
    )
    assert state.absent(IQN)["result"] is True
    delete.assert_not_called()


def test_absent_requires_confirmation_and_redacts_current(monkeypatch):
    current = target(
        auth={
            "user": "chapuser1",
            "password": "oldprivate12",
            "mutual_user": "",
            "mutual_password": "",
        }
    )
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": Mock(return_value=envelope([{"target_iqn": IQN}])),
            "ceph_iscsi.get_target": Mock(return_value=envelope(current)),
            "ceph_iscsi.delete_target": delete,
        },
    )
    result = state.absent(IQN)
    assert result["result"] is False
    assert "oldprivate12" not in repr(result)
    delete.assert_not_called()


def test_absent_deletes_and_verifies(monkeypatch):
    lists = Mock(side_effect=[envelope([{"target_iqn": IQN}]), envelope([])])
    delete = Mock(return_value=envelope(None, 204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_iscsi.list_targets": lists,
            "ceph_iscsi.get_target": Mock(return_value=envelope(target())),
            "ceph_iscsi.delete_target": delete,
        },
    )
    result = state.absent(IQN, confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with(IQN, confirm=True, profile="default")


def test_invalid_iqn_fails_before_read(monkeypatch):
    listing = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_iscsi.list_targets": listing})
    result = state.absent("invalid")
    assert result["result"] is False
    listing.assert_not_called()
