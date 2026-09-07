"""Pure event helper behavior."""

from datetime import datetime
from datetime import timezone
from types import SimpleNamespace

import pytest

from saltext.ceph.utils.ceph import events


def as_dict(value) -> dict:
    assert isinstance(value, dict)
    return value


def test_render_config_merges_list_entries_without_mutating_input():
    config = [{"profile": "lab"}, {"interval": 30}]
    assert events.render_config(config) == {"profile": "lab", "interval": 30}
    assert config == [{"profile": "lab"}, {"interval": 30}]


@pytest.mark.parametrize(
    "config",
    (
        {},
        ["bad"],
        [None],
        [{1: True}],
        [{"bad\nkey": True}],
        [{"x" * 129: True}],
        [{}] * (events.MAX_CONFIG_ENTRIES + 1),
    ),
)
def test_render_config_rejects_non_list_or_non_mapping_entries(config):
    with pytest.raises(ValueError):
        events.render_config(config)


@pytest.mark.parametrize(
    "config, expected",
    (
        ([{"unknown": True}], "unsupported option"),
        ([{"profile": ""}], "profile"),
        ([{"profile": "bad\nname"}], "profile"),
        ([{"interval": True}], "interval"),
        ([{"interval": 0}], "interval"),
        ([{"interval": float("inf")}], "interval"),
        ([{"run_once": "yes"}], "run_once"),
        ([{"beacon_module": ""}], "beacon_module"),
        ([{"beacon_module": "x" * 129}], "beacon_module"),
        ([{"_beacon_name": "bad\nname"}], "_beacon_name"),
    ),
)
def test_validate_config_rejects_invalid_common_options(config, expected):
    rendered, error = events.validate_config(config, set())
    assert rendered is None
    assert expected in error


def test_validate_config_accepts_salt_runtime_options():
    rendered, error = events.validate_config(
        [
            {"profile": "lab"},
            {"interval": 30.5},
            {"disable_during_state_run": True},
            {"beacon_module": "ceph_health"},
            {"_beacon_name": "cluster_health"},
        ],
        set(),
    )
    assert error is None
    assert rendered["profile"] == "lab"


def test_response_data_accepts_object_envelope_and_raw_body():
    assert events.response_data(SimpleNamespace(status=200, data={"a": 1})) == {"a": 1}
    assert events.response_data({"status": 200, "data": [1], "headers": {}}) == [1]
    assert events.response_data({"health": {}}) == {"health": {}}


@pytest.mark.parametrize(
    "response",
    (
        SimpleNamespace(status=500, data={"secret": "value"}),
        {"status": 401, "data": {"token": "secret"}},
        {"status": True, "data": {}},
        {"status": "200", "data": {}},
    ),
)
def test_response_data_rejects_unsuccessful_or_invalid_envelopes(response):
    with pytest.raises(ValueError, match="status"):
        events.response_data(response)


def test_fingerprint_is_deterministic_and_rejects_non_json_values():
    assert events.fingerprint({"b": 2, "a": 1}) == events.fingerprint({"a": 1, "b": 2})
    assert events.fingerprint({"a": 1}) != events.fingerprint({"a": 2})
    with pytest.raises(ValueError):
        events.fingerprint({"bad": object()})
    with pytest.raises(ValueError):
        events.fingerprint(float("nan"))
    with pytest.raises(ValueError):
        events.fingerprint({"large": "x" * 100}, max_bytes=16)


def test_context_state_is_namespaced_repairs_own_slot_and_bounds_instances():
    context = {"unrelated": {"keep": True}, events.CONTEXT_KEY: "invalid"}
    first = events.context_state(context, "ceph_health", "first")
    first["status"] = "ok"
    assert context["unrelated"] == {"keep": True}
    assert events.context_state(context, "ceph_health", "first")["status"] == "ok"
    for number in range(events.MAX_CONTEXT_INSTANCES + 2):
        events.context_state(context, "ceph_health", str(number))
    root = as_dict(context[events.CONTEXT_KEY])
    bucket = root.get("ceph_health")  # pylint: disable=no-member
    assert isinstance(bucket, dict)
    assert len(bucket) == events.MAX_CONTEXT_INSTANCES


def test_context_state_uses_ephemeral_mapping_for_invalid_context():
    assert events.context_state(None, "ceph_health", "one") == {}


def test_health_observation_supports_minimal_and_snapshot_check_shapes():
    minimal = {
        "health": {
            "status": "HEALTH_WARN",
            "checks": [
                {
                    "type": "OSD_DOWN",
                    "severity": "HEALTH_WARN",
                    "summary": {"message": "one OSD is down", "count": 1},
                }
            ],
        }
    }
    snapshot = {
        "health": {
            "status": "HEALTH_ERR",
            "checks": {
                "MON_DOWN": {
                    "severity": "HEALTH_ERR",
                    "summary": {"message": "monitor unavailable", "count": 1},
                    "muted": False,
                }
            },
        }
    }
    assert events.health_observation(minimal, 10)["checks"][0]["name"] == "OSD_DOWN"
    assert events.health_observation(snapshot, 10)["checks"][0]["name"] == "MON_DOWN"


def test_health_observation_caps_event_checks_but_fingerprints_all_checks():
    data = {
        "health": {
            "status": "HEALTH_WARN",
            "checks": [
                {"type": "A", "summary": {"message": "first"}},
                {"type": "B", "summary": {"message": "second"}},
            ],
        }
    }
    observation = events.health_observation(data, 1)
    assert observation["check_count"] == 2
    assert len(observation["checks"]) == 1
    changed = {"health": {**data["health"], "checks": data["health"]["checks"][:1]}}
    assert events.health_observation(changed, 1)["fingerprint"] != observation["fingerprint"]


def test_health_observation_is_deterministic_and_reports_count_above_internal_cap():
    checks = {
        f"CHECK_{number:04d}": {"summary": {"message": str(number)}}
        for number in reversed(range(events.MAX_HEALTH_CHECKS + 1))
    }
    first = events.health_observation({"health": {"status": "HEALTH_WARN", "checks": checks}}, 1)
    reordered = dict(reversed(list(checks.items())))
    second = events.health_observation(
        {"health": {"status": "HEALTH_WARN", "checks": reordered}}, 1
    )
    assert first["check_count"] == events.MAX_HEALTH_CHECKS + 1
    assert first["fingerprint"] == second["fingerprint"]


@pytest.mark.parametrize(
    "data",
    ({}, {"health": []}, {"health": {"status": ""}}, {"health": {"status": "OK", "checks": 1}}),
)
def test_health_observation_rejects_malformed_payloads(data):
    with pytest.raises(ValueError):
        events.health_observation(data, 10)


def test_task_identity_uses_private_metadata_but_event_redacts_it():
    task = {
        "name": "service/create",
        "metadata": {"password": "secret"},
        "begin_time": "2026-01-01T00:00:00Z",
        "end_time": "2026-01-01T00:00:01Z",
        "duration": 1,
        "progress": 100,
        "success": False,
        "exception": "secret failure",
        "ret_value": {"token": "secret"},
    }
    identity = events.task_identity(task)
    other = events.task_identity({**task, "metadata": {"password": "different"}})
    assert identity != other
    event = events.task_event(task)
    assert event["success"] is False
    assert event["duration"] == 1
    assert "metadata" not in event
    assert "exception" not in event
    assert "ret_value" not in event
    assert "secret" not in repr(event)


@pytest.mark.parametrize(
    "task",
    (
        {},
        {"name": "task", "success": "false"},
        {
            "name": "task\nsecret",
            "success": False,
            "metadata": {},
            "begin_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:00:01Z",
            "duration": 1,
        },
        {
            "name": "task",
            "success": False,
            "metadata": {"value": "x" * events.MAX_TASK_METADATA_BYTES},
            "begin_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:00:01Z",
            "duration": 1,
        },
        [],
    ),
)
def test_task_identity_rejects_malformed_tasks(task):
    with pytest.raises(ValueError):
        events.task_identity(task)


def test_days_until_accepts_aware_naive_and_zulu_timestamps():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert events.days_until("2026-01-03T12:00:00Z", now) == 2
    assert events.days_until("2026-01-03T12:00:00", now) == 2
    assert events.days_until("invalid", now) is None


@pytest.mark.parametrize(
    "entry, expected",
    (
        ({"cert_name": "a", "status": "expired", "days_to_expiration": 50}, "expired"),
        ({"cert_name": "a", "status": "invalid"}, "critical"),
        ({"cert_name": "a", "status": "valid", "days_to_expiration": 5}, "critical"),
        ({"cert_name": "a", "status": "expiring", "days_to_expiration": 20}, "warning"),
        ({"cert_name": "a", "status": "valid", "days_to_expiration": 40}, "healthy"),
    ),
)
def test_certificate_observation_classifies_api_fallback_days(entry, expected):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _, level, observation = events.certificate_observation(entry, 30, 7, now)
    assert level == expected
    assert set(observation).issuperset({"certificate_id", "cert_name", "status"})


def test_certificate_observation_treats_unknown_status_as_critical():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _, level, observation = events.certificate_observation(
        {"cert_name": "rgw_ssl_cert", "status": "future_status"}, 30, 7, now
    )
    assert level == "critical"
    assert observation["status"] == "future_status"


def test_certificate_observation_recalculates_days_from_expiry_date():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entry = {
        "cert_name": "rgw_ssl_cert",
        "status": "valid",
        "days_to_expiration": 999,
        "expiry_date": "2026-01-06T00:00:00Z",
    }
    _, level, observation = events.certificate_observation(entry, 30, 7, now)
    assert level == "critical"
    assert observation["days_to_expiration"] == 5


def test_bounded_certificates_sorts_and_caps_results():
    entries = [{"cert_name": "bad\nname", "status": "valid"}] + [
        {"cert_name": f"cert-{number:04d}", "status": "valid"}
        for number in reversed(range(events.MAX_CERTIFICATES + 1))
    ]
    result = events.bounded_certificates(entries)
    assert len(result) == events.MAX_CERTIFICATES
    assert result[0]["cert_name"] == "cert-0000"
    with pytest.raises(ValueError):
        events.bounded_certificates([None])
