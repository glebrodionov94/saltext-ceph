"""Ceph host state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_host as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def host(address="10.0.0.1", labels=None, status=""):
    return {
        "hostname": "node1",
        "addr": address,
        "labels": labels or [],
        "status": status,
    }


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_present_is_idempotent_with_orderless_labels(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": Mock(return_value=envelope([host(labels=["b", "a"])])),
            "ceph_host.create": create,
        },
    )
    result = state.present("node1", address="10.0.0.1", labels=["a", "b"], maintenance=False)
    assert result["result"] is True
    create.assert_not_called()


def test_present_plans_creation_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([])), "ceph_host.create": create},
    )
    result = state.present("node1", labels=["storage"])
    assert result["result"] is None
    create.assert_not_called()


def test_present_creates_waits_and_verifies(monkeypatch):
    list_ = Mock(
        side_effect=[
            envelope([]),
            envelope([host(labels=["storage"])]),
            envelope([host(labels=["storage"])]),
        ]
    )
    create = Mock(
        return_value=envelope({"name": "host/add", "metadata": {"hostname": "node1"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": list_, "ceph_host.create": create, "ceph_task.wait": wait},
    )
    result = state.present("node1", labels=["storage"])
    assert result["result"] is True
    create.assert_called_once_with(
        "node1",
        address=None,
        labels=["storage"],
        maintenance=False,
        profile="default",
    )
    wait.assert_called_once()


def test_present_updates_labels_then_maintenance(monkeypatch):
    list_ = Mock(
        side_effect=[
            envelope([host(labels=[])]),
            envelope([host(labels=["storage"])]),
            envelope([host(labels=["storage"], status="maintenance")]),
        ]
    )
    set_labels = Mock(return_value=envelope(status=204))
    toggle = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": list_,
            "ceph_host.set_labels": set_labels,
            "ceph_host.toggle_maintenance": toggle,
        },
    )
    result = state.present("node1", labels=["storage"], maintenance=True)
    assert result["result"] is True
    set_labels.assert_called_once()
    toggle.assert_called_once_with("node1", force=False, profile="default")


def test_existing_address_mismatch_is_known_failure_even_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([host()]))},
    )
    result = state.present("node1", address="10.0.0.2")
    assert result["result"] is False
    assert "cannot update" in result["comment"]


def test_absent_plans_without_confirmation_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([host()])), "ceph_host.delete": delete},
    )
    assert state.absent("node1")["result"] is None
    delete.assert_not_called()


def test_absent_requires_confirmation_for_live_delete(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([host()])), "ceph_host.delete": delete},
    )
    result = state.absent("node1")
    assert result["result"] is False
    delete.assert_not_called()


def test_absent_deletes_waits_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([host()]), envelope([])])
    delete = Mock(
        return_value=envelope({"name": "host/remove", "metadata": {"hostname": "node1"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": list_, "ceph_host.delete": delete, "ceph_task.wait": wait},
    )
    result = state.absent("node1", confirm=True)
    assert result["result"] is True
    delete.assert_called_once()
    wait.assert_called_once()


def test_absent_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([])), "ceph_host.delete": delete},
    )
    assert state.absent("node1")["result"] is True
    delete.assert_not_called()
