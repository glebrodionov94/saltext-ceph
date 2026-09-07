"""Dashboard settings state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_settings as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def setting(value, default=45, **extra):
    return {
        "name": "REST_REQUESTS_TIMEOUT",
        "type": "int",
        "value": value,
        "default": default,
        **extra,
    }


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_virtual_requires_execution_functions(monkeypatch):
    assert state.__virtual__()[0] is False
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_settings.get": Mock(),
            "ceph_settings.set": Mock(),
            "ceph_settings.delete": Mock(),
        },
    )
    assert state.__virtual__() == "ceph_settings"


def test_managed_is_idempotent_for_canonical_json(monkeypatch):
    set_ = Mock()
    current = setting({"b": [2, 1], "a": True}, default={})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_settings.get": Mock(return_value=envelope(current)), "ceph_settings.set": set_},
    )
    result = state.managed("rest-requests-timeout", {"a": True, "b": [2, 1]})
    assert result["result"] is True
    assert not result["changes"]
    set_.assert_not_called()


def test_managed_distinguishes_boolean_and_integer_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_settings.get": Mock(return_value=envelope(setting(True))),
            "ceph_settings.set": set_,
        },
    )
    result = state.managed("REST_REQUESTS_TIMEOUT", 1)
    assert result["result"] is None
    assert result["changes"] == {"old": True, "new": 1}
    set_.assert_not_called()


def test_managed_sets_waits_for_202_and_post_reads(monkeypatch):
    get = Mock(side_effect=[envelope(setting(45)), envelope(setting(60))])
    set_ = Mock(
        return_value=envelope(
            {"name": "settings/set", "metadata": {"name": "REST_REQUESTS_TIMEOUT"}},
            202,
        )
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_settings.get": get, "ceph_settings.set": set_, "ceph_task.wait": wait},
    )
    result = state.managed("rest-requests-timeout", 60)
    assert result["result"] is True
    assert result["changes"] == {"old": 45, "new": 60}
    set_.assert_called_once_with("REST_REQUESTS_TIMEOUT", value=60, profile="default")
    wait.assert_called_once()


def test_failed_post_read_is_a_state_failure(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_settings.get": Mock(return_value=envelope(setting(45))),
            "ceph_settings.set": Mock(return_value=envelope(status=200)),
        },
    )
    result = state.managed("REST_REQUESTS_TIMEOUT", 60)
    assert result["result"] is False
    assert "did not converge" in result["comment"]


def test_secret_named_setting_is_rejected_before_read_or_write(monkeypatch):
    get = Mock()
    set_ = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_settings.get": get, "ceph_settings.set": set_})
    result = state.managed("GRAFANA_API_PASSWORD", "private-value")
    assert result["result"] is False
    assert "private-value" not in repr(result)
    assert not result["changes"]
    get.assert_not_called()
    set_.assert_not_called()


def test_structured_sensitive_keys_are_rejected_without_leaking_value(monkeypatch):
    get = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_settings.get": get})
    result = state.managed("MULTICLUSTER_CONFIG", {"remote": {"token": "private-value"}})
    assert result["result"] is False
    assert "private-value" not in repr(result)
    assert not result["changes"]
    get.assert_not_called()


def test_redacted_current_setting_is_not_treated_as_idempotent(monkeypatch):
    current = setting("***********", default="***********", redacted=True)
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_settings.get": Mock(return_value=envelope(current))},
    )
    result = state.managed("REST_REQUESTS_TIMEOUT", "private-value")
    assert result["result"] is False
    assert "private-value" not in repr(result)
    assert not result["changes"]


def test_sensitive_key_in_reported_default_cannot_enter_reset_diff(monkeypatch):
    current = setting(60, default={"api_key": "server-private"})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_settings.get": Mock(return_value=envelope(current))},
    )
    result = state.default("REST_REQUESTS_TIMEOUT")
    assert result["result"] is False
    assert "server-private" not in repr(result)
    assert not result["changes"]


def test_default_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_settings.get": Mock(return_value=envelope(setting(45))),
            "ceph_settings.delete": delete,
        },
    )
    result = state.default("REST_REQUESTS_TIMEOUT")
    assert result["result"] is True
    delete.assert_not_called()


def test_default_test_mode_plans_without_confirmation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_settings.get": Mock(return_value=envelope(setting(60))),
            "ceph_settings.delete": delete,
        },
    )
    result = state.default("REST_REQUESTS_TIMEOUT")
    assert result["result"] is None
    assert result["changes"] == {"old": 60, "new": 45}
    delete.assert_not_called()


def test_default_requires_confirmation_then_resets_and_verifies(monkeypatch):
    get = Mock(side_effect=[envelope(setting(60)), envelope(setting(60)), envelope(setting(45))])
    delete = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_settings.get": get, "ceph_settings.delete": delete},
    )
    assert state.default("REST_REQUESTS_TIMEOUT")["result"] is False
    delete.assert_not_called()
    result = state.default("REST_REQUESTS_TIMEOUT", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with("REST_REQUESTS_TIMEOUT", profile="default")
