"""Declarative RBD mirroring states."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_rbd_mirroring as state

PEER_UUID = "0f7c66c4-3366-4c0c-84da-f94103ef8266"


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def task():
    return envelope({"name": "rbd/mirroring", "metadata": {"pool_name": "rbd"}}, 202)


def peer(**changes):
    value = {
        "uuid": PEER_UUID,
        "cluster_name": "remote",
        "site_name": "remote",
        "client_id": "mirror",
        "mon_host": "v2:192.0.2.10:3300",
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_virtual_requires_complete_execution_surface(monkeypatch):
    monkeypatch.setattr(state, "__salt__", {"ceph_rbd_mirroring.get_site_name": Mock()})
    result = state.__virtual__()
    assert result[0] is False
    assert "ceph_rbd_mirroring.create_peer" in result[1]


def test_site_name_is_idempotent(monkeypatch):
    setter = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.get_site_name": Mock(
                return_value=envelope({"site_name": "site-a"})
            ),
            "ceph_rbd_mirroring.set_site_name": setter,
        },
    )
    assert not state.site_name_managed("site-a")["changes"]
    setter.assert_not_called()


def test_site_name_test_mode_plans_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    setter = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.get_site_name": Mock(return_value=envelope({"site_name": "old"})),
            "ceph_rbd_mirroring.set_site_name": setter,
        },
    )
    result = state.site_name_managed("site-a")
    assert result["result"] is None
    setter.assert_not_called()


def test_site_name_waits_and_post_reads(monkeypatch):
    get = Mock(
        side_effect=[
            envelope({"site_name": "old"}),
            envelope({"site_name": "site-a"}),
        ]
    )
    setter = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.get_site_name": get,
            "ceph_rbd_mirroring.set_site_name": setter,
            "ceph_task.wait": wait,
        },
    )
    result = state.site_name_managed("site-a")
    assert result["result"] is True
    wait.assert_called_once()
    assert get.call_count == 2


def test_pool_mode_disable_requires_confirm_but_test_mode_previews(monkeypatch):
    setter = Mock()
    salt = {
        "ceph_rbd_mirroring.get_pool_mode": Mock(return_value=envelope({"mirror_mode": "image"})),
        "ceph_rbd_mirroring.set_pool_mode": setter,
    }
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.pool_mode_managed("rbd", "disabled")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    setter.assert_not_called()
    monkeypatch.setattr(state, "__opts__", {"test": True})
    assert state.pool_mode_managed("rbd", "disabled")["result"] is None


def test_pool_mode_waits_and_verifies(monkeypatch):
    get = Mock(
        side_effect=[
            envelope({"mirror_mode": "disabled"}),
            envelope({"mirror_mode": "image"}),
        ]
    )
    setter = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.get_pool_mode": get,
            "ceph_rbd_mirroring.set_pool_mode": setter,
            "ceph_task.wait": wait,
        },
    )
    assert state.pool_mode_managed("rbd", "image")["result"] is True
    setter.assert_called_once_with("rbd", "image", confirm=False, profile="default")
    wait.assert_called_once()


def test_pool_mode_rejects_unknown_read_value(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.get_pool_mode": Mock(
                return_value=envelope({"mirror_mode": "future-mode"})
            )
        },
    )
    result = state.pool_mode_managed("rbd", "image")
    assert result["result"] is False
    assert "unknown mode" in result["comment"]


def test_peer_present_is_idempotent_and_whitelists_public_fields(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.list_peers": Mock(return_value=envelope([PEER_UUID])),
            "ceph_rbd_mirroring.get_peer": Mock(
                return_value=envelope(peer(key="must-not-leak", token="must-not-leak"))
            ),
            "ceph_rbd_mirroring.update_peer": update,
        },
    )
    result = state.peer_present("remote", "rbd", "mirror", mon_host="v2:192.0.2.10:3300")
    assert result["result"] is True
    assert "must-not-leak" not in str(result)
    update.assert_not_called()


def test_peer_create_test_mode_validates_key_file_without_disclosure(monkeypatch, tmp_path):
    source = tmp_path / "peer.key"
    source.write_text("secret-peer-key", encoding="utf-8")
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.list_peers": Mock(return_value=envelope([])),
            "ceph_rbd_mirroring.create_peer": create,
        },
    )
    result = state.peer_present("remote", "rbd", "mirror", key_source=str(source.resolve()))
    assert result["result"] is None
    assert str(source.resolve()) not in str(result)
    assert "secret-peer-key" not in str(result)
    create.assert_not_called()


def test_peer_create_waits_and_post_reads(monkeypatch, tmp_path):
    source = tmp_path / "peer.key"
    source.write_text("secret-peer-key", encoding="utf-8")
    lists = Mock(side_effect=[envelope([]), envelope([PEER_UUID])])
    create = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.list_peers": lists,
            "ceph_rbd_mirroring.get_peer": Mock(return_value=envelope(peer(mon_host=""))),
            "ceph_rbd_mirroring.create_peer": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.peer_present("remote", "rbd", "mirror", key_source=str(source.resolve()))
    assert result["result"] is True
    assert str(source.resolve()) not in str(result)
    assert "secret-peer-key" not in str(result)
    assert create.call_args.kwargs["key_source"] == str(source.resolve())
    wait.assert_called_once()


def test_existing_peer_key_is_bootstrap_only_and_is_not_read_or_rotated(monkeypatch):
    missing_path = "C:/definitely/missing/peer.key"
    update = Mock(return_value=envelope(status=200))
    get = Mock(
        side_effect=[
            envelope(peer(client_id="old")),
            envelope(peer(client_id="new")),
        ]
    )
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.list_peers": Mock(
                side_effect=[envelope([PEER_UUID]), envelope([PEER_UUID])]
            ),
            "ceph_rbd_mirroring.get_peer": get,
            "ceph_rbd_mirroring.update_peer": update,
        },
    )
    result = state.peer_present(
        "remote",
        "rbd",
        "new",
        mon_host="v2:192.0.2.10:3300",
        key_source=missing_path,
    )
    assert result["result"] is True
    assert update.call_args.kwargs["key_source"] is None
    assert update.call_args.kwargs["clear_key"] is False
    assert missing_path not in str(result)


def test_duplicate_peer_identity_fails_without_mutation(monkeypatch):
    second = "e9eeac33-cb72-42b5-bf48-4ed4eb006e45"
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.list_peers": Mock(return_value=envelope([PEER_UUID, second])),
            "ceph_rbd_mirroring.get_peer": Mock(
                side_effect=[envelope(peer()), envelope(peer(uuid=second))]
            ),
            "ceph_rbd_mirroring.create_peer": create,
        },
    )
    result = state.peer_present("remote", "rbd", "mirror")
    assert result["result"] is False
    assert "ambiguous" in result["comment"]
    create.assert_not_called()


def test_peer_absent_confirmation_and_post_read(monkeypatch):
    delete = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    lists = Mock(side_effect=[envelope([PEER_UUID]), envelope([])])
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.list_peers": lists,
            "ceph_rbd_mirroring.get_peer": Mock(return_value=envelope(peer())),
            "ceph_rbd_mirroring.delete_peer": delete,
            "ceph_task.wait": wait,
        },
    )
    assert state.peer_absent("remote", "rbd")["result"] is False
    delete.assert_not_called()
    lists.side_effect = [envelope([PEER_UUID]), envelope([])]
    result = state.peer_absent("remote", "rbd", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with("rbd", PEER_UUID, confirm=True, profile="default")
    wait.assert_called_once()


def test_peer_nonconvergence_returns_normal_state_failure(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rbd_mirroring.list_peers": Mock(side_effect=[envelope([]), envelope([])]),
            "ceph_rbd_mirroring.create_peer": Mock(return_value=envelope(status=201)),
        },
    )
    result = state.peer_present("remote", "rbd", "mirror")
    assert result["result"] is False
    assert "did not converge" in result["comment"]
