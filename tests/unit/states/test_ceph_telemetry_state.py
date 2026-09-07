"""Ceph telemetry state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_telemetry as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_virtual_requires_read_and_mutation_functions(monkeypatch):
    assert state.__virtual__()[0] is False
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_mgr_module.get_config": Mock(), "ceph_telemetry.set": Mock()},
    )
    assert state.__virtual__() == "ceph_telemetry"


def test_managed_is_idempotent(monkeypatch):
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.get_config": Mock(
                return_value=envelope({"enabled": True, "contact": "ignored"})
            ),
            "ceph_telemetry.set": set_,
        },
    )
    result = state.managed("telemetry", True, license_name="sharing-1-0")
    assert result["result"] is True
    assert not result["changes"]
    set_.assert_not_called()


@pytest.mark.parametrize(
    "enabled,license_name",
    ((True, None), (True, "wrong"), (False, "sharing-1-0"), (1, None)),
)
def test_invalid_consent_fails_before_read(monkeypatch, enabled, license_name):
    read = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_mgr_module.get_config": read})
    result = state.managed("telemetry", enabled, license_name=license_name)
    assert result["result"] is False
    read.assert_not_called()


def test_managed_plans_exact_change_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.get_config": Mock(return_value=envelope({"enabled": False})),
            "ceph_telemetry.set": set_,
        },
    )
    result = state.managed("telemetry", True, license_name="sharing-1-0")
    assert result["result"] is None
    assert result["changes"] == {
        "old": {"enabled": False},
        "new": {"enabled": True},
    }
    set_.assert_not_called()


def test_managed_enables_waits_for_202_and_post_reads(monkeypatch):
    read = Mock(
        side_effect=[
            envelope({"enabled": False}),
            envelope({"enabled": True}),
        ]
    )
    set_ = Mock(
        return_value=envelope({"name": "telemetry/set", "metadata": {"enabled": True}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.get_config": read,
            "ceph_telemetry.set": set_,
            "ceph_task.wait": wait,
        },
    )
    result = state.managed("telemetry", True, license_name="sharing-1-0")
    assert result["result"] is True
    set_.assert_called_once_with(enable=True, license_name="sharing-1-0", profile="default")
    wait.assert_called_once()
    assert read.call_count == 2


def test_managed_disables_without_license(monkeypatch):
    read = Mock(side_effect=[envelope({"enabled": True}), envelope({"enabled": False})])
    set_ = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_mgr_module.get_config": read, "ceph_telemetry.set": set_},
    )
    result = state.managed("telemetry", False)
    assert result["result"] is True
    set_.assert_called_once_with(enable=False, license_name=None, profile="default")


def test_malformed_or_nonconverged_post_read_fails(monkeypatch):
    read = Mock(side_effect=[envelope({"enabled": False}), envelope({"enabled": False})])
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.get_config": read,
            "ceph_telemetry.set": Mock(return_value=envelope(status=200)),
        },
    )
    result = state.managed("telemetry", True, license_name="sharing-1-0")
    assert result["result"] is False
    assert "did not converge" in result["comment"]

    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_mgr_module.get_config": Mock(return_value=envelope({"enabled": "yes"}))},
    )
    malformed = state.managed("telemetry", False)
    assert malformed["result"] is False
    assert "boolean" in malformed["comment"]
