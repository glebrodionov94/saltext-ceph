"""Declarative NFS export state tests."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_nfs as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def export(**changes):
    value = {
        "export_id": 7,
        "cluster_id": "nfs1",
        "path": "/volumes/team/data",
        "pseudo": "/team/data",
        "access_type": "RW",
        "squash": "root_squash",
        "security_label": False,
        "protocols": [4],
        "transports": ["TCP"],
        "fsal": {"name": "CEPH", "fs_name": "cephfs", "user_id": "server-managed"},
        "clients": [],
    }
    value.update(changes)
    return value


def desired_kwargs(**changes):
    value = {
        "cluster_id": "nfs1",
        "path": "/volumes/team/data",
        "fsal": {"name": "CEPH", "fs_name": "cephfs"},
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_present_is_idempotent_and_ignores_server_managed_fsal_fields(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nfs.list_exports": Mock(return_value=envelope([export()])),
            "ceph_nfs.update_export": update,
        },
    )
    result = state.present("/team/data", **desired_kwargs())
    assert result["result"] is True
    update.assert_not_called()


def test_present_plans_create_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nfs.list_exports": Mock(return_value=envelope([])),
            "ceph_nfs.create_export": create,
        },
    )
    result = state.present("/team/data", **desired_kwargs())
    assert result["result"] is None
    create.assert_not_called()


def test_present_creates_waits_and_post_reads(monkeypatch):
    listing = Mock(side_effect=[envelope([]), envelope([export()])])
    create = Mock(
        return_value=envelope({"name": "nfs/create", "metadata": {"cluster_id": "nfs1"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nfs.list_exports": listing,
            "ceph_nfs.create_export": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.present("/team/data", **desired_kwargs())
    assert result["result"] is True
    assert create.call_args.kwargs["cluster_id"] == "nfs1"
    assert create.call_args.kwargs["protocols"] == [4]
    wait.assert_called_once()


def test_present_updates_full_public_configuration(monkeypatch):
    before = export(access_type="RO")
    update = Mock(return_value=envelope({}, 200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nfs.list_exports": Mock(side_effect=[envelope([before]), envelope([export()])]),
            "ceph_nfs.update_export": update,
        },
    )
    result = state.present("/team/data", **desired_kwargs())
    assert result["result"] is True
    assert update.call_args.args[:2] == ("nfs1", 7)
    assert update.call_args.kwargs["access_type"] == "RW"


def test_present_fails_on_duplicate_logical_identity(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nfs.list_exports": Mock(return_value=envelope([export(), export(export_id=8)]))},
    )
    result = state.present("/team/data", **desired_kwargs())
    assert result["result"] is False
    assert "duplicate" in result["comment"]


def test_present_reports_failed_postcondition(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nfs.list_exports": Mock(side_effect=[envelope([]), envelope([])]),
            "ceph_nfs.create_export": Mock(return_value=envelope({}, 201)),
        },
    )
    result = state.present("/team/data", **desired_kwargs())
    assert result["result"] is False
    assert "did not converge" in result["comment"]


def test_absent_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nfs.list_exports": Mock(return_value=envelope([])),
            "ceph_nfs.delete_export": delete,
        },
    )
    assert state.absent("/team/data", "nfs1")["result"] is True
    delete.assert_not_called()


def test_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nfs.list_exports": Mock(return_value=envelope([export()])),
            "ceph_nfs.delete_export": delete,
        },
    )
    assert state.absent("/team/data", "nfs1")["result"] is False
    delete.assert_not_called()


def test_absent_deletes_waits_and_verifies(monkeypatch):
    delete = Mock(return_value=envelope({"name": "nfs/delete", "metadata": {"export_id": 7}}, 202))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nfs.list_exports": Mock(side_effect=[envelope([export()]), envelope([])]),
            "ceph_nfs.delete_export": delete,
            "ceph_task.wait": wait,
        },
    )
    result = state.absent("/team/data", "nfs1", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with("nfs1", 7, confirm=True, profile="default")
    wait.assert_called_once()


def test_invalid_pseudo_fails_before_read(monkeypatch):
    listing = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_nfs.list_exports": listing})
    result = state.absent("/bad/../path", "nfs1")
    assert result["result"] is False
    listing.assert_not_called()
