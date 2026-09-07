"""Ceph manager module state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_mgr_module as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def module(enabled=False, always_on=False):
    return [{"name": "prometheus", "enabled": enabled, "always_on": always_on}]


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_managed_is_idempotent(monkeypatch):
    enable = Mock()
    set_config = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.list": Mock(return_value=envelope(module(True))),
            "ceph_mgr_module.get_config": Mock(return_value=envelope({"server_port": 9283})),
            "ceph_mgr_module.enable": enable,
            "ceph_mgr_module.set_config": set_config,
        },
    )
    result = state.managed("prometheus", enabled=True, config={"server_port": 9283})
    assert result["result"] is True
    enable.assert_not_called()
    set_config.assert_not_called()


def test_managed_plans_and_redacts_secrets(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    set_config = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.list": Mock(return_value=envelope(module())),
            "ceph_mgr_module.get_config": Mock(return_value=envelope({"password": "old"})),
            "ceph_mgr_module.set_config": set_config,
        },
    )
    result = state.managed("prometheus", config={"password": "new"}, secret_options=["password"])
    assert result["result"] is None
    assert result["changes"]["old"]["config"]["password"] == "********"
    assert "'password': 'new'" not in repr(result)
    set_config.assert_not_called()


def test_managed_sets_config_enables_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope(module(False)), envelope(module(True))])
    get_config = Mock(
        side_effect=[envelope({"server_port": 9000}), envelope({"server_port": 9283})]
    )
    set_config = Mock(return_value=envelope(status=204))
    enable = Mock(
        return_value=envelope(
            {"name": "mgr_module/enable", "metadata": {"module_name": "prometheus"}},
            202,
        )
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.list": list_,
            "ceph_mgr_module.get_config": get_config,
            "ceph_mgr_module.set_config": set_config,
            "ceph_mgr_module.enable": enable,
            "ceph_task.wait": wait,
        },
    )
    result = state.managed(
        "prometheus", enabled=True, config={"server_port": 9283}, force_enable=True
    )
    assert result["result"] is True
    set_config.assert_called_once()
    enable.assert_called_once_with("prometheus", force=True, profile="default")
    wait.assert_called_once()


def test_managed_disables_module(monkeypatch):
    list_ = Mock(side_effect=[envelope(module(True)), envelope(module(False))])
    disable = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_mgr_module.list": list_, "ceph_mgr_module.disable": disable},
    )
    result = state.managed("prometheus", enabled=False)
    assert result["result"] is True
    disable.assert_called_once_with("prometheus", profile="default")


def test_null_config_option_is_verified_as_absent(monkeypatch):
    list_ = Mock(return_value=envelope(module()))
    get_config = Mock(side_effect=[envelope({"server_addr": "::"}), envelope({})])
    set_config = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.list": list_,
            "ceph_mgr_module.get_config": get_config,
            "ceph_mgr_module.set_config": set_config,
        },
    )
    result = state.managed("prometheus", config={"server_addr": None})
    assert result["result"] is True


def test_always_on_module_cannot_be_disabled(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_mgr_module.list": Mock(return_value=envelope(module(True, True)))},
    )
    result = state.managed("prometheus", enabled=False)
    assert result["result"] is False
    assert "always on" in result["comment"]


def test_missing_module_is_state_failure(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_mgr_module.list": Mock(return_value=envelope([]))},
    )
    assert state.managed("prometheus", enabled=True)["result"] is False


def test_failed_post_read_is_state_failure(monkeypatch):
    list_ = Mock(return_value=envelope(module(False)))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_mgr_module.list": list_,
            "ceph_mgr_module.enable": Mock(return_value=envelope(status=204)),
        },
    )
    result = state.managed("prometheus", enabled=True)
    assert result["result"] is False
    assert "did not converge" in result["comment"]


def test_invalid_secret_options_fail_before_write(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_mgr_module.list": Mock(return_value=envelope(module()))},
    )
    result = state.managed("prometheus", config={"server_port": 9283}, secret_options=["password"])
    assert result["result"] is False
