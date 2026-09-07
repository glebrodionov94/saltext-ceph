"""CRUSH rule state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_crush_rule as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def rule(failure_domain="host", device_class="ssd"):
    take = "default" + (f"~{device_class}" if device_class else "")
    return {
        "rule_name": "replicated_ssd",
        "type": 1,
        "steps": [
            {"op": "take", "item_name": take},
            {"op": "chooseleaf_firstn", "type": failure_domain},
            {"op": "emit"},
        ],
    }


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
            "ceph_crush_rule.list": Mock(return_value=envelope([rule()])),
            "ceph_crush_rule.create": create,
        },
    )
    result = state.present("replicated_ssd", "host", device_class="ssd", root="default")
    assert result["result"] is True
    create.assert_not_called()


def test_present_creates_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([]), envelope([rule()])])
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_crush_rule.list": list_, "ceph_crush_rule.create": create},
    )
    result = state.present("replicated_ssd", "host", device_class="ssd", root="default")
    assert result["result"] is True
    create.assert_called_once()


def test_drift_requires_replace(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_crush_rule.list": Mock(return_value=envelope([rule("rack")]))},
    )
    result = state.present("replicated_ssd", "host", device_class="ssd", root="default")
    assert result["result"] is False
    assert "immutable" in result["comment"]


def test_replace_requires_confirmation_live(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_crush_rule.list": Mock(return_value=envelope([rule("rack")]))},
    )
    result = state.present(
        "replicated_ssd", "host", device_class="ssd", root="default", replace=True
    )
    assert result["result"] is False
    assert "confirm" in result["comment"]


def test_replace_deletes_creates_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([rule("rack")]), envelope([rule()])])
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_crush_rule.list": list_,
            "ceph_crush_rule.delete": delete,
            "ceph_crush_rule.create": create,
        },
    )
    result = state.present(
        "replicated_ssd",
        "host",
        device_class="ssd",
        root="default",
        replace=True,
        confirm=True,
    )
    assert result["result"] is True
    delete.assert_called_once()
    create.assert_called_once()


def test_absent_requires_confirmation_and_then_deletes(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    list_ = Mock(side_effect=[envelope([rule()]), envelope([])])
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_crush_rule.list": list_, "ceph_crush_rule.delete": delete},
    )
    assert state.absent("replicated_ssd")["result"] is False
    delete.assert_not_called()
    list_.reset_mock(side_effect=True)
    list_.side_effect = [envelope([rule()]), envelope([])]
    assert state.absent("replicated_ssd", confirm=True)["result"] is True


def test_test_mode_plans_replacement(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_crush_rule.list": Mock(return_value=envelope([rule("rack")]))},
    )
    result = state.present(
        "replicated_ssd", "host", device_class="ssd", root="default", replace=True
    )
    assert result["result"] is None


def test_absent_is_idempotent(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_crush_rule.list": Mock(return_value=envelope([]))},
    )
    assert state.absent("replicated_ssd")["result"] is True
