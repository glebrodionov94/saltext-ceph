"""Ceph health beacon transitions."""

from unittest.mock import Mock

import pytest

from saltext.ceph.beacons import ceph_health


def envelope(status="HEALTH_OK", checks=None):
    return {
        "status": 200,
        "data": {"health": {"status": status, "checks": checks or []}},
        "headers": {},
    }


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(ceph_health, "__context__", {}, raising=False)
    monkeypatch.setattr(ceph_health, "__salt__", {}, raising=False)
    monkeypatch.setattr(ceph_health.log, "warning", Mock())


@pytest.mark.parametrize(
    "config, expected",
    (
        ({}, "must be a list"),
        ([{"profile": ""}], "profile"),
        ([{"interval": 0}], "interval"),
        ([{"max_checks": 0}], "max_checks"),
        ([{"max_checks": 101}], "max_checks"),
        ([{"max_checks": True}], "max_checks"),
        ([{"typo": True}], "unsupported"),
    ),
)
def test_validate_rejects_invalid_configuration(config, expected):
    valid, message = ceph_health.validate(config)
    assert valid is False
    assert expected in message


def test_validate_accepts_defaults_profile_and_interval():
    assert ceph_health.validate([])[0] is True
    assert ceph_health.validate([{"profile": "lab"}, {"interval": 30}])[0] is True


def test_health_transitions_are_fingerprinted_and_each_run_reads_once(monkeypatch):
    read = Mock(
        side_effect=[
            envelope(),
            envelope(
                "HEALTH_WARN",
                [{"type": "OSD_DOWN", "summary": {"message": "one down"}}],
            ),
            envelope(
                "HEALTH_WARN",
                [{"type": "OSD_DOWN", "summary": {"message": "one down"}}],
            ),
            envelope(
                "HEALTH_WARN",
                [{"type": "OSD_DOWN", "summary": {"message": "two down"}}],
            ),
            envelope(),
        ]
    )
    monkeypatch.setattr(ceph_health, "__salt__", {"ceph_health.minimal": read})

    assert not ceph_health.beacon([])
    first = ceph_health.beacon([])
    assert [item["tag"] for item in first] == ["degraded"]
    assert first[0]["checks"][0]["name"] == "OSD_DOWN"
    assert not ceph_health.beacon([])
    changed = ceph_health.beacon([])
    assert [item["tag"] for item in changed] == ["degraded"]
    recovered = ceph_health.beacon([])
    assert [item["tag"] for item in recovered] == ["recovered"]
    assert read.call_count == 5
    assert all(call.kwargs == {"profile": "default"} for call in read.call_args_list)


def test_unreachable_and_reachable_are_edge_triggered(monkeypatch):
    read = Mock(side_effect=[RuntimeError("secret"), RuntimeError("secret"), envelope()])
    monkeypatch.setattr(ceph_health, "__salt__", {"ceph_health.minimal": read})

    first = ceph_health.beacon([{"profile": "lab"}])
    assert first == [
        {
            "tag": "unreachable",
            "profile": "lab",
            "error": "Ceph Dashboard health read failed",
        }
    ]
    assert "secret" not in repr(first)
    assert not ceph_health.beacon([{"profile": "lab"}])
    assert [item["tag"] for item in ceph_health.beacon([{"profile": "lab"}])] == ["reachable"]
    assert read.call_count == 3


def test_reachability_recovery_can_also_emit_health_recovery(monkeypatch):
    read = Mock(
        side_effect=[
            envelope("HEALTH_ERR", [{"type": "MON_DOWN"}]),
            RuntimeError("offline"),
            envelope(),
        ]
    )
    monkeypatch.setattr(ceph_health, "__salt__", {"ceph_health.minimal": read})
    assert ceph_health.beacon([])[0]["tag"] == "degraded"
    assert ceph_health.beacon([])[0]["tag"] == "unreachable"
    assert [item["tag"] for item in ceph_health.beacon([])] == ["reachable", "recovered"]


def test_named_instances_do_not_share_fingerprint_cache(monkeypatch):
    read = Mock(return_value=envelope("HEALTH_WARN", [{"type": "OSD_DOWN"}]))
    monkeypatch.setattr(ceph_health, "__salt__", {"ceph_health.minimal": read})
    one = [{"_beacon_name": "cluster_one"}]
    two = [{"_beacon_name": "cluster_two"}]
    assert ceph_health.beacon(one)[0]["tag"] == "degraded"
    assert not ceph_health.beacon(one)
    assert ceph_health.beacon(two)[0]["tag"] == "degraded"


def test_max_checks_bounds_event_and_invalid_config_does_not_read(monkeypatch):
    read = Mock(return_value=envelope("HEALTH_WARN", [{"type": "A"}, {"type": "B"}, {"type": "C"}]))
    monkeypatch.setattr(ceph_health, "__salt__", {"ceph_health.minimal": read})
    event = ceph_health.beacon([{"max_checks": 2}])[0]
    assert len(event["checks"]) == 2
    assert event["check_count"] == 3
    assert not ceph_health.beacon([{"max_checks": 0}])
    assert read.call_count == 1
