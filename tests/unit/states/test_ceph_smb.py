"""Declarative SMB state tests."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_smb as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def cluster(**changes):
    value = {
        "resource_type": "ceph.smb.cluster",
        "cluster_id": "files",
        "intent": "present",
        "auth_mode": "user",
        "user_group_settings": [{"source_type": "resource", "ref": "local-users"}],
    }
    value.update(changes)
    return value


def share(**changes):
    value = {
        "resource_type": "ceph.smb.share",
        "cluster_id": "files",
        "share_id": "home",
        "intent": "present",
        "name": "Home",
        "readonly": False,
        "cephfs": {"volume": "cephfs", "path": "/home"},
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_cluster_present_is_idempotent(monkeypatch):
    current = cluster(extra_server_field=True)
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.list_clusters": Mock(return_value=envelope([current])),
            "ceph_smb.create_cluster": create,
        },
    )
    desired = cluster()
    desired.pop("cluster_id")
    result = state.cluster_present("files", desired)
    assert result["result"] is True
    assert not result["changes"]
    create.assert_not_called()


def test_cluster_present_plans_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.list_clusters": Mock(return_value=envelope([])),
            "ceph_smb.create_cluster": create,
        },
    )
    result = state.cluster_present("files", {"auth_mode": "user"})
    assert result["result"] is None
    create.assert_not_called()


def test_cluster_present_applies_and_verifies(monkeypatch):
    desired = cluster()
    lists = Mock(side_effect=[envelope([]), envelope([desired])])
    create = Mock(return_value=envelope({}, 201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_smb.list_clusters": lists, "ceph_smb.create_cluster": create},
    )
    resource = dict(desired)
    resource.pop("cluster_id")
    result = state.cluster_present("files", resource)
    assert result["result"] is True
    create.assert_called_once_with(desired, profile="default")


def test_cluster_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.list_clusters": Mock(return_value=envelope([cluster()])),
            "ceph_smb.delete_cluster": delete,
        },
    )
    result = state.cluster_absent("files")
    assert result["result"] is False
    delete.assert_not_called()


def test_cluster_absent_deletes_and_verifies(monkeypatch):
    delete = Mock(return_value=envelope(None, 204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.list_clusters": Mock(side_effect=[envelope([cluster()]), envelope([])]),
            "ceph_smb.delete_cluster": delete,
        },
    )
    assert state.cluster_absent("files", confirm=True)["result"] is True
    delete.assert_called_once_with("files", confirm=True, profile="default")


def test_share_present_updates_drift_and_verifies(monkeypatch):
    before = share(readonly=True)
    after = share()
    create = Mock(return_value=envelope({}, 201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.list_shares": Mock(side_effect=[envelope([before]), envelope([after])]),
            "ceph_smb.create_share": create,
        },
    )
    resource = share()
    resource.pop("share_id")
    result = state.share_present("home", "files", resource)
    assert result["result"] is True
    create.assert_called_once_with(after, profile="default")


def test_share_present_rejects_mismatched_cluster(monkeypatch):
    listing = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_smb.list_shares": listing})
    result = state.share_present("home", "files", share(cluster_id="other"))
    assert result["result"] is False
    listing.assert_not_called()


def test_share_absent_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_smb.list_shares": Mock(return_value=envelope([])), "ceph_smb.delete_share": delete},
    )
    assert state.share_absent("home", "files")["result"] is True
    delete.assert_not_called()


def test_share_absent_test_mode_does_not_require_confirmation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.list_shares": Mock(return_value=envelope([share()])),
            "ceph_smb.delete_share": delete,
        },
    )
    assert state.share_absent("home", "files")["result"] is None
    delete.assert_not_called()


def test_share_qos_is_idempotent(monkeypatch):
    update = Mock()
    current = share(cephfs={"volume": "cephfs", "path": "/home", "qos": {"read_iops_limit": 1000}})
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.get_share": Mock(return_value=envelope(current)),
            "ceph_smb.update_share_qos": update,
        },
    )
    assert state.share_qos("home", "files", read_iops_limit=1000)["result"] is True
    update.assert_not_called()


def test_share_qos_updates_and_post_reads(monkeypatch):
    before = share(cephfs={"volume": "cephfs", "qos": {}})
    after = share(cephfs={"volume": "cephfs", "qos": {"read_iops_limit": 1000}})
    update = Mock(return_value=envelope({}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.get_share": Mock(side_effect=[envelope(before), envelope(after)]),
            "ceph_smb.update_share_qos": update,
        },
    )
    result = state.share_qos("home", "files", read_iops_limit=1000)
    assert result["result"] is True
    update.assert_called_once_with("files", "home", profile="default", read_iops_limit=1000)


def test_share_qos_reports_failed_postcondition(monkeypatch):
    current = share(cephfs={"volume": "cephfs", "qos": {}})
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_smb.get_share": Mock(side_effect=[envelope(current), envelope(current)]),
            "ceph_smb.update_share_qos": Mock(return_value=envelope({})),
        },
    )
    result = state.share_qos("home", "files", write_delay_max=30)
    assert result["result"] is False
    assert "did not converge" in result["comment"]
