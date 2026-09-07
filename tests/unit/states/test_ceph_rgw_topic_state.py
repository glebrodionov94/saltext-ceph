"""Declarative RGW topic state tests."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_rgw_topic as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def topic(**changes):
    value = {
        "name": "events",
        "owner": "alice",
        "key": "alice:events",
        "dest": {
            "push_endpoint": "***********",
            "persistent": True,
            "time_to_live": "60",
            "max_retries": "3",
            "retry_sleep_duration": "5",
        },
        "opaqueData": "***********",
        "policy": '{"Statement":[]}',
    }
    value.update(changes)
    return value


def desired(**changes):
    value = {
        "owner": "alice",
        "persistent": True,
        "time_to_live": "60",
        "max_retries": "3",
        "retry_sleep_duration": "5",
        "policy": {"Statement": []},
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_present_is_idempotent_and_ignores_masked_transport_fields(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_topic.list_topics": Mock(return_value=envelope([topic()])),
            "ceph_rgw_topic.create_topic": create,
        },
    )
    result = state.present("events", push_endpoint_source=None, **desired())
    assert result["result"] is True
    create.assert_not_called()


def test_present_plans_create_without_secret_in_changes(monkeypatch, tmp_path):
    secret = tmp_path / "endpoint"
    secret.write_text("https://user:password@example.test", encoding="utf-8")
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_topic.list_topics": Mock(return_value=envelope([])),
            "ceph_rgw_topic.create_topic": create,
        },
    )
    monkeypatch.setattr(state, "__opts__", {"test": True})
    result = state.present("events", "alice", push_endpoint_source=str(secret), persistent=True)
    assert result["result"] is None
    assert "password" not in str(result)
    assert "push_endpoint" not in result["changes"]["new"]
    create.assert_not_called()


def test_present_rejects_readable_drift_without_replace(monkeypatch):
    before = topic(dest={**topic()["dest"], "max_retries": "2"})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_topic.list_topics": Mock(return_value=envelope([before]))},
    )
    result = state.present("events", **desired())
    assert result["result"] is False
    assert "replace=True" in result["comment"]


def test_present_replaces_only_with_confirmation_and_post_reads(monkeypatch):
    before = topic(dest={**topic()["dest"], "max_retries": "2"})
    listing = Mock(side_effect=[envelope([before]), envelope([topic()])])
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_topic.list_topics": listing,
            "ceph_rgw_topic.delete_topic": delete,
            "ceph_rgw_topic.create_topic": create,
        },
    )
    result = state.present("events", replace=True, confirm_replace=True, **desired())
    assert result["result"] is True
    delete.assert_called_once_with("alice:events", confirm=True, profile="default")
    assert create.call_args.kwargs["include_secrets"] is False


def test_present_live_replace_requires_confirmation(monkeypatch):
    before = topic(dest={**topic()["dest"], "max_retries": "2"})
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_topic.list_topics": Mock(return_value=envelope([before])),
            "ceph_rgw_topic.delete_topic": delete,
        },
    )
    result = state.present("events", replace=True, **desired())
    assert result["result"] is False
    assert "confirm_replace" in result["comment"]
    delete.assert_not_called()


def test_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_topic.list_topics": Mock(return_value=envelope([topic()])),
            "ceph_rgw_topic.delete_topic": delete,
        },
    )
    result = state.absent("events", owner="alice")
    assert result["result"] is False
    delete.assert_not_called()


def test_absent_deletes_waits_and_verifies(monkeypatch):
    listing = Mock(side_effect=[envelope([topic()]), envelope([])])
    delete = Mock(
        return_value=envelope(
            {"name": "rgw/topic/delete", "metadata": {"key": "alice:events"}}, 202
        )
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_topic.list_topics": listing,
            "ceph_rgw_topic.delete_topic": delete,
            "ceph_task.wait": wait,
        },
    )
    result = state.absent("events", owner="alice", confirm=True)
    assert result["result"] is True
    wait.assert_called_once()


def test_duplicate_topic_identity_is_rejected(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_topic.list_topics": Mock(return_value=envelope([topic(), topic()]))},
    )
    result = state.absent("events", owner="alice")
    assert result["result"] is False
    assert "duplicate" in result["comment"]


def test_present_rejects_non_scalar_retry_value(monkeypatch):
    monkeypatch.setattr(state, "__salt__", {})
    result = state.present("events", "alice", max_retries={"unexpected": 3})
    assert result["result"] is False
    assert "text or an integer" in result["comment"]
