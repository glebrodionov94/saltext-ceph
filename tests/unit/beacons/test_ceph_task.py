"""Ceph task completion beacon behavior."""

from unittest.mock import Mock

import pytest

from saltext.ceph.beacons import ceph_task


def finished(name, success, suffix, **extra):
    return {
        "name": name,
        "metadata": {"private": f"secret-{suffix}"},
        "begin_time": f"2026-01-01T00:00:{suffix}Z",
        "end_time": f"2026-01-01T00:01:{suffix}Z",
        "duration": 60,
        "progress": 100,
        "success": success,
        **extra,
    }


def envelope(tasks):
    return {
        "status": 200,
        "data": {"executing_tasks": [], "finished_tasks": tasks},
        "headers": {},
    }


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(ceph_task, "__context__", {}, raising=False)
    monkeypatch.setattr(ceph_task, "__salt__", {}, raising=False)
    monkeypatch.setattr(ceph_task.log, "warning", Mock())


@pytest.mark.parametrize(
    "config, expected",
    (
        ({}, "must be a list"),
        ([{"name": ""}], "name"),
        ([{"name": "bad\nname"}], "name"),
        ([{"failures_only": "yes"}], "failures_only"),
        ([{"emit_existing": 1}], "emit_existing"),
        ([{"cache_size": 0}], "cache_size"),
        ([{"cache_size": 257}], "cache_size"),
        ([{"cache_size": True}], "cache_size"),
        ([{"interval": -1}], "interval"),
    ),
)
def test_validate_rejects_invalid_configuration(config, expected):
    valid, message = ceph_task.validate(config)
    assert valid is False
    assert expected in message


def test_validate_accepts_defaults_and_bounded_cache():
    assert ceph_task.validate([])[0] is True
    assert ceph_task.validate([{"cache_size": 256}, {"failures_only": False}])[0]


def test_first_run_baselines_then_new_failure_emits_once(monkeypatch):
    old = finished("pool/create", False, "01")
    new = finished(
        "service/create",
        False,
        "02",
        exception="password=secret",
        ret_value={"token": "secret"},
    )
    read = Mock(side_effect=[envelope([old]), envelope([new, old]), envelope([new, old])])
    monkeypatch.setattr(ceph_task, "__salt__", {"ceph_task.list": read})

    assert not ceph_task.beacon([])
    result = ceph_task.beacon([])
    assert [item["tag"] for item in result] == ["failed"]
    assert result[0]["name"] == "service/create"
    assert "metadata" not in result[0]
    assert "exception" not in result[0]
    assert "ret_value" not in result[0]
    assert "secret" not in repr(result)
    assert not ceph_task.beacon([])
    assert read.call_count == 3


def test_failures_only_default_caches_success_without_emitting(monkeypatch):
    success = finished("service/create", True, "03")
    read = Mock(side_effect=[envelope([]), envelope([success]), envelope([success])])
    monkeypatch.setattr(ceph_task, "__salt__", {"ceph_task.list": read})
    assert not ceph_task.beacon([])
    assert not ceph_task.beacon([])
    assert not ceph_task.beacon([])


def test_failures_only_false_emits_success_and_passes_filter(monkeypatch):
    success = finished("service/create", True, "04")
    read = Mock(side_effect=[envelope([]), envelope([success])])
    monkeypatch.setattr(ceph_task, "__salt__", {"ceph_task.list": read})
    config = [
        {"name": "service/create"},
        {"profile": "lab"},
        {"failures_only": False},
    ]
    assert not ceph_task.beacon(config)
    result = ceph_task.beacon(config)
    assert [item["tag"] for item in result] == ["succeeded"]
    read.assert_called_with(name="service/create", profile="lab")


def test_emit_existing_reports_existing_failures_on_first_run(monkeypatch):
    read = Mock(return_value=envelope([finished("pool/delete", False, "05")]))
    monkeypatch.setattr(ceph_task, "__salt__", {"ceph_task.list": read})
    result = ceph_task.beacon([{"emit_existing": True}])
    assert [item["tag"] for item in result] == ["failed"]


def test_cache_and_work_are_bounded_by_configured_size(monkeypatch):
    tasks = [finished("task", False, f"{number:02d}") for number in range(5)]
    read = Mock(return_value=envelope(list(reversed(tasks))))
    monkeypatch.setattr(ceph_task, "__salt__", {"ceph_task.list": read})
    config = [{"cache_size": 2}, {"emit_existing": True}]
    result = ceph_task.beacon(config)
    assert len(result) == 2
    context = getattr(ceph_task, "__context__")
    root = context["saltext.ceph.beacons"]["ceph_task"]
    state = next(iter(root.values()))
    assert len(state["seen"]) == 2


def test_malformed_tasks_are_ignored_and_read_failure_is_suppressed(monkeypatch):
    read = Mock(side_effect=[envelope([{"name": "bad"}, None]), RuntimeError("secret")])
    monkeypatch.setattr(ceph_task, "__salt__", {"ceph_task.list": read})
    assert not ceph_task.beacon([{"emit_existing": True}])
    assert not ceph_task.beacon([{"emit_existing": True}])
    assert read.call_count == 2


def test_invalid_config_never_calls_execution_module(monkeypatch):
    read = Mock()
    monkeypatch.setattr(ceph_task, "__salt__", {"ceph_task.list": read})
    assert not ceph_task.beacon([{"cache_size": 999}])
    read.assert_not_called()
