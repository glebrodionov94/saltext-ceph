"""Erasure-code profile state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_erasure_code_profile as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def profile(k=4):
    return {"name": "ec42", "plugin": "jerasure", "k": k, "m": 2}


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_present_is_idempotent(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_erasure_code_profile.list": Mock(return_value=envelope([profile()])),
            "ceph_erasure_code_profile.create": create,
        },
    )
    result = state.present("ec42", {"plugin": "jerasure", "k": 4, "m": 2})
    assert result["result"] is True
    create.assert_not_called()


def test_present_creates_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([]), envelope([profile()])])
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_erasure_code_profile.list": list_, "ceph_erasure_code_profile.create": create},
    )
    assert state.present("ec42", {"plugin": "jerasure", "k": 4, "m": 2})["result"] is True


def test_drift_requires_explicit_replace(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_erasure_code_profile.list": Mock(return_value=envelope([profile(3)]))},
    )
    result = state.present("ec42", {"plugin": "jerasure", "k": 4, "m": 2})
    assert result["result"] is False
    assert "immutable" in result["comment"]


def test_replace_deletes_creates_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([profile(3)]), envelope([profile(4)])])
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_erasure_code_profile.list": list_,
            "ceph_erasure_code_profile.delete": delete,
            "ceph_erasure_code_profile.create": create,
        },
    )
    result = state.present(
        "ec42", {"plugin": "jerasure", "k": 4, "m": 2}, replace=True, confirm=True
    )
    assert result["result"] is True
    delete.assert_called_once()
    create.assert_called_once()


def test_replace_requires_confirmation(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_erasure_code_profile.list": Mock(return_value=envelope([profile(3)]))},
    )
    result = state.present("ec42", {"plugin": "jerasure", "k": 4, "m": 2}, replace=True)
    assert result["result"] is False


def test_absent_deletes_with_confirmation(monkeypatch):
    list_ = Mock(side_effect=[envelope([profile()]), envelope([])])
    delete = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_erasure_code_profile.list": list_, "ceph_erasure_code_profile.delete": delete},
    )
    assert state.absent("ec42", confirm=True)["result"] is True


def test_absent_is_idempotent(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_erasure_code_profile.list": Mock(return_value=envelope([]))},
    )
    assert state.absent("ec42")["result"] is True
