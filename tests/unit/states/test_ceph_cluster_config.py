"""Ceph configuration state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_cluster_config as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def item(values):
    return {
        "name": "debug_ms",
        "value": [{"section": section, "value": value} for section, value in values.items()],
    }


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_managed_is_idempotent_and_preserves_unmanaged_sections(monkeypatch):
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_cluster_config.list": Mock(
                return_value=envelope([item({"mon": "0/3", "osd": "0/5"})])
            ),
            "ceph_cluster_config.set": set_,
        },
    )
    result = state.managed("debug_ms", [{"section": "mon", "value": "0/3"}])
    assert result["result"] is True
    assert not result["changes"]
    set_.assert_not_called()


def test_managed_plans_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_cluster_config.list": Mock(return_value=envelope([item({"mon": "0/3"})])),
            "ceph_cluster_config.set": set_,
        },
    )
    result = state.managed("debug_ms", [{"section": "mon", "value": "1/5"}])
    assert result["result"] is None
    assert result["changes"] == {"old": {"mon": "0/3"}, "new": {"mon": "1/5"}}
    set_.assert_not_called()


def test_managed_updates_waits_and_verifies(monkeypatch):
    list_ = Mock(
        side_effect=[
            envelope([item({"mon": "0/3"})]),
            envelope([item({"mon": "1/5"})]),
        ]
    )
    set_ = Mock(
        return_value=envelope(
            {"name": "cluster_configuration/create", "metadata": {"name": "debug_ms"}},
            202,
        )
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_cluster_config.list": list_,
            "ceph_cluster_config.set": set_,
            "ceph_task.wait": wait,
        },
    )
    result = state.managed("debug_ms", [{"section": "mon", "value": "1/5"}])
    assert result["result"] is True
    set_.assert_called_once_with(
        "debug_ms",
        [{"section": "mon", "value": "1/5"}],
        force_update=None,
        profile="default",
    )
    wait.assert_called_once()


def test_replace_removes_undeclared_sections(monkeypatch):
    list_ = Mock(
        side_effect=[
            envelope([item({"mon": "0/3", "osd": "0/5"})]),
            envelope([item({"mon": "0/3"})]),
        ]
    )
    set_ = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_cluster_config.list": list_, "ceph_cluster_config.set": set_},
    )
    result = state.managed("debug_ms", [{"section": "mon", "value": "0/3"}], replace=True)
    assert result["result"] is True
    assert {"section": "osd", "value": None} in set_.call_args.args[1]


def test_null_value_removes_managed_section(monkeypatch):
    list_ = Mock(side_effect=[envelope([item({"mon": "0/3"})]), envelope([item({})])])
    set_ = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_cluster_config.list": list_, "ceph_cluster_config.set": set_},
    )
    result = state.managed("debug_ms", [{"section": "mon", "value": None}])
    assert result["result"] is True
    assert not result["changes"]["new"]


def test_absent_removes_one_section_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([item({"mon": "0/3"})]), envelope([item({})])])
    remove = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_cluster_config.list": list_, "ceph_cluster_config.remove": remove},
    )
    result = state.absent("debug_ms", "mon")
    assert result["result"] is True
    remove.assert_called_once_with("debug_ms", "mon", profile="default")


def test_absent_is_idempotent(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_cluster_config.list": Mock(return_value=envelope([item({})])),
            "ceph_cluster_config.remove": remove,
        },
    )
    assert state.absent("debug_ms", "mon")["result"] is True
    remove.assert_not_called()


def test_failed_verification_returns_false(monkeypatch):
    list_ = Mock(return_value=envelope([item({"mon": "0/3"})]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_cluster_config.list": list_,
            "ceph_cluster_config.set": Mock(return_value=envelope(status=201)),
        },
    )
    result = state.managed("debug_ms", [{"section": "mon", "value": "1/5"}])
    assert result["result"] is False
    assert "did not converge" in result["comment"]


def test_invalid_declaration_fails_before_read(monkeypatch):
    list_ = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_cluster_config.list": list_})
    assert state.managed("bad?name", [{"section": "mon", "value": 1}])["result"] is False
    list_.assert_not_called()
