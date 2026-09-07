"""Tests for the direct master-side Ceph runner."""

from unittest.mock import Mock

import pytest
from salt.exceptions import SaltRunnerError

from saltext.ceph.runners import ceph
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(ceph, "__opts__", {"ceph": {"profiles": {}}}, raising=False)
    monkeypatch.setattr(ceph, "__context__", {}, raising=False)


def test_virtual_name():
    assert ceph.__virtual__() == "ceph"


def test_ping_returns_safe_response_envelope(monkeypatch):
    client = Mock()
    monkeypatch.setattr(ceph, "_client", Mock(return_value=client))
    monkeypatch.setattr(
        ceph.health,
        "fsid",
        Mock(return_value=APIResponse(200, "11111111-1111-1111-1111-111111111111")),
    )
    assert ceph.ping() == {
        "status": 200,
        "data": "11111111-1111-1111-1111-111111111111",
        "headers": {},
    }
    ceph.health.fsid.assert_called_once_with(client)


def test_tasks_passes_filter_and_profile(monkeypatch):
    client = Mock()
    get_client = Mock(return_value=client)
    monkeypatch.setattr(ceph.ceph_utils, "get_client", get_client)
    monkeypatch.setattr(
        ceph.task,
        "list_",
        Mock(return_value=APIResponse(200, {"executing_tasks": [], "finished_tasks": []})),
    )
    result = ceph.tasks("pool/create", profile="lab")
    assert result["status"] == 200
    get_client.assert_called_once_with(ceph.__opts__, {}, ceph.__context__, "lab")
    ceph.task.list_.assert_called_once_with(client, "pool/create", False)


def test_wait_task_forwards_bounds(monkeypatch):
    client = Mock()
    monkeypatch.setattr(ceph, "_client", Mock(return_value=client))
    waiter = Mock(return_value=APIResponse(200, {"success": True}))
    monkeypatch.setattr(ceph.task, "wait", waiter)
    ceph.wait_task(
        "service/create",
        {"service_name": "mgr"},
        timeout=10,
        interval=0.5,
        fail_on_error=False,
    )
    waiter.assert_called_once_with(
        client,
        "service/create",
        {"service_name": "mgr"},
        10,
        0.5,
        False,
        False,
    )


def test_task_diagnostics_require_explicit_secret_opt_in(monkeypatch):
    client = Mock()
    monkeypatch.setattr(ceph, "_client", Mock(return_value=client))
    lister = Mock(return_value=APIResponse(200, {"executing_tasks": [], "finished_tasks": []}))
    waiter = Mock(return_value=APIResponse(200, {"success": True}))
    monkeypatch.setattr(ceph.task, "list_", lister)
    monkeypatch.setattr(ceph.task, "wait", waiter)

    ceph.tasks(include_secrets=True)
    ceph.wait_task("service/create", include_secrets=True)

    lister.assert_called_once_with(client, None, True)
    waiter.assert_called_once_with(client, "service/create", None, 300.0, 2.0, True, True)


def test_ceph_errors_become_runner_errors(monkeypatch):
    monkeypatch.setattr(ceph, "_client", Mock(return_value=Mock()))
    monkeypatch.setattr(ceph.health, "fsid", Mock(side_effect=ConfigurationError("bad profile")))
    with pytest.raises(SaltRunnerError, match="bad profile"):
        ceph.ping()


def test_profile_errors_become_runner_errors(monkeypatch):
    monkeypatch.setattr(
        ceph.ceph_utils,
        "get_client",
        Mock(side_effect=ConfigurationError("missing profile")),
    )
    with pytest.raises(SaltRunnerError, match="missing profile"):
        ceph.tasks()


def test_clear_cache_uses_runner_context(monkeypatch):
    clear = Mock(return_value=True)
    monkeypatch.setattr(ceph.ceph_utils, "clear_cache", clear)
    assert ceph.clear_cache(None) is True
    clear.assert_called_once_with(ceph.__context__, None)


@pytest.mark.parametrize("profile", ("", "bad\nprofile", "x" * 129, [], True))
def test_runner_rejects_invalid_profile_before_cache_access(monkeypatch, profile):
    clear = Mock()
    monkeypatch.setattr(ceph.ceph_utils, "clear_cache", clear)
    with pytest.raises(SaltRunnerError, match="profile"):
        ceph.clear_cache(profile)
    clear.assert_not_called()
