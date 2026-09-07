"""CephX user state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_users as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def current(caps=None):
    return {"entity": "client.backup", "caps": caps or {"mon": "allow r"}}


def test_virtual_requires_execution_functions(monkeypatch):
    assert state.__virtual__()[0] is False
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_users.get": Mock(),
            "ceph_users.create": Mock(),
            "ceph_users.update": Mock(),
            "ceph_users.delete": Mock(),
        },
    )
    assert state.__virtual__() == "ceph_users"


def test_present_is_idempotent_for_mapping_caps(monkeypatch):
    get = Mock(return_value=envelope(current()))
    create = Mock()
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_users.get": get, "ceph_users.create": create, "ceph_users.update": update},
    )
    result = state.present("client.backup", [{"entity": "mon", "cap": "allow r"}])
    assert result["result"] is True
    assert not result["changes"]
    create.assert_not_called()
    update.assert_not_called()


def test_present_plans_create_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_users.get": Mock(return_value=envelope()), "ceph_users.create": create},
    )
    result = state.present("client.backup", [{"entity": "mon", "cap": "allow r"}])
    assert result["result"] is None
    assert result["changes"]["old"] is None
    create.assert_not_called()


def test_present_creates_waits_and_verifies(monkeypatch):
    desired = current({"mon": "allow rw"})
    get = Mock(side_effect=[envelope(), envelope(desired)])
    create = Mock(
        return_value=envelope({"name": "auth/create", "metadata": {"entity": "client.backup"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_users.get": get, "ceph_users.create": create, "ceph_task.wait": wait},
    )
    result = state.present("client.backup", [{"entity": "mon", "cap": "allow rw"}])
    assert result["result"] is True
    create.assert_called_once()
    wait.assert_called_once()


def test_present_updates_changed_capabilities(monkeypatch):
    before = current({"mon": "allow r"})
    after = current({"mon": "allow rw"})
    update = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_users.get": Mock(side_effect=[envelope(before), envelope(after)]),
            "ceph_users.update": update,
        },
    )
    result = state.present("client.backup", [{"entity": "mon", "cap": "allow rw"}])
    assert result["result"] is True
    update.assert_called_once()


def test_present_reports_failed_verification(monkeypatch):
    before = current({"mon": "allow r"})
    update = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_users.get": Mock(side_effect=[envelope(before), envelope(before)]),
            "ceph_users.update": update,
        },
    )
    result = state.present("client.backup", [{"entity": "mon", "cap": "allow rw"}])
    assert result["result"] is False
    assert "did not converge" in result["comment"]


def test_absent_deletes_and_verifies(monkeypatch):
    before = current()
    delete = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_users.get": Mock(side_effect=[envelope(before), envelope()]),
            "ceph_users.delete": delete,
        },
    )
    result = state.absent("client.backup", confirm=True)
    assert result["result"] is True
    assert result["changes"]["new"] is None
    delete.assert_called_once_with("client.backup", confirm=True, profile="default")


def test_absent_requires_confirmation_before_delete(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_users.get": Mock(return_value=envelope(current())),
            "ceph_users.delete": delete,
        },
    )
    result = state.absent("client.backup")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    delete.assert_not_called()


def test_absent_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_users.get": Mock(return_value=envelope()), "ceph_users.delete": delete},
    )
    assert state.absent("client.backup")["result"] is True
    delete.assert_not_called()


def test_invalid_capabilities_return_state_failure_before_read(monkeypatch):
    get = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_users.get": get})
    result = state.present("client.backup", [])
    assert result["result"] is False
    get.assert_not_called()
