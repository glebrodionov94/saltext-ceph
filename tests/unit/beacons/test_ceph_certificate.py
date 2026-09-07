"""Ceph certificate expiry beacon transitions."""

from datetime import datetime
from datetime import timezone
from unittest.mock import Mock

import pytest

from saltext.ceph.beacons import ceph_certificate
from saltext.ceph.utils.ceph import events

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def certificate(expiry, status="valid", **extra):
    return {
        "cert_name": "rgw_ssl_cert",
        "scope": "SERVICE",
        "target": "rgw.site",
        "status": status,
        "expiry_date": expiry,
        "days_to_expiration": 999,
        **extra,
    }


def envelope(certificates):
    return {"status": 200, "data": certificates, "headers": {}}


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(ceph_certificate, "__context__", {}, raising=False)
    monkeypatch.setattr(ceph_certificate, "__salt__", {}, raising=False)
    monkeypatch.setattr(ceph_certificate.log, "warning", Mock())
    monkeypatch.setattr(events, "utcnow", Mock(return_value=NOW))


@pytest.mark.parametrize(
    "config, expected",
    (
        ({}, "must be a list"),
        ([{"warning_days": -1}], "warning_days"),
        ([{"critical_days": 3651}], "critical_days"),
        ([{"warning_days": 5}, {"critical_days": 6}], "must not exceed"),
        ([{"scope": "cluster"}], "scope"),
        ([{"service_type": "rgw,status=bad"}], "service_type"),
        ([{"include_cephadm_signed": "yes"}], "include_cephadm_signed"),
        ([{"interval": 0}], "interval"),
    ),
)
def test_validate_rejects_invalid_configuration(config, expected):
    valid, message = ceph_certificate.validate(config)
    assert valid is False
    assert expected in message


def test_validate_accepts_defaults_and_filters():
    assert ceph_certificate.validate([])[0] is True
    assert ceph_certificate.validate(
        [{"scope": "HOST"}, {"service_type": "rgw*"}, {"interval": 3600}]
    )[0]


def test_warning_critical_expired_and_recovered_transitions(monkeypatch):
    read = Mock(
        side_effect=[
            envelope([certificate("2026-01-21T00:00:00Z")]),
            envelope([certificate("2026-01-21T00:00:00Z")]),
            envelope([certificate("2026-01-06T00:00:00Z")]),
            envelope([certificate("2025-12-31T00:00:00Z", status="expired")]),
            envelope([certificate("2026-03-01T00:00:00Z")]),
        ]
    )
    monkeypatch.setattr(ceph_certificate, "__salt__", {"ceph_certificates.list": read})
    assert [item["tag"] for item in ceph_certificate.beacon([])] == ["warning"]
    assert not ceph_certificate.beacon([])
    assert [item["tag"] for item in ceph_certificate.beacon([])] == ["critical"]
    assert [item["tag"] for item in ceph_certificate.beacon([])] == ["expired"]
    assert [item["tag"] for item in ceph_certificate.beacon([])] == ["recovered"]
    assert read.call_count == 5


def test_each_cycle_uses_one_filtered_metadata_read(monkeypatch):
    read = Mock(return_value=envelope([]))
    monkeypatch.setattr(ceph_certificate, "__salt__", {"ceph_certificates.list": read})
    config = [
        {"profile": "lab"},
        {"scope": "service"},
        {"service_type": "rgw*"},
        {"include_cephadm_signed": False},
    ]
    assert not ceph_certificate.beacon(config)
    read.assert_called_once_with(
        status=None,
        scope="service",
        service_type="rgw*",
        include_cephadm_signed=False,
        profile="lab",
    )


def test_event_excludes_pem_details_and_subject_data(monkeypatch):
    entry = certificate(
        "2026-01-03T00:00:00Z",
        certificate="-----BEGIN CERTIFICATE-----\nsecret",
        private_key="secret",
        details={"subject": "secret"},
        issuer="secret",
        common_name="secret",
    )
    read = Mock(return_value=envelope([entry]))
    monkeypatch.setattr(ceph_certificate, "__salt__", {"ceph_certificates.list": read})
    result = ceph_certificate.beacon([])
    assert result[0]["tag"] == "critical"
    assert "secret" not in repr(result)
    assert "certificate" not in result[0]
    assert "private_key" not in result[0]
    context = repr(getattr(ceph_certificate, "__context__"))
    assert "BEGIN CERTIFICATE" not in context
    assert "secret" not in context


def test_clock_progression_changes_warning_to_critical(monkeypatch):
    read = Mock(return_value=envelope([certificate("2026-01-10T00:00:00Z")]))
    monkeypatch.setattr(ceph_certificate, "__salt__", {"ceph_certificates.list": read})
    monkeypatch.setattr(
        events,
        "utcnow",
        Mock(
            side_effect=[
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 4, tzinfo=timezone.utc),
            ]
        ),
    )
    assert ceph_certificate.beacon([])[0]["tag"] == "warning"
    assert ceph_certificate.beacon([])[0]["tag"] == "critical"


def test_invalid_status_without_expiry_is_critical(monkeypatch):
    entry = certificate("", status="invalid")
    read = Mock(return_value=envelope([entry]))
    monkeypatch.setattr(ceph_certificate, "__salt__", {"ceph_certificates.list": read})
    assert ceph_certificate.beacon([])[0]["tag"] == "critical"


def test_unknown_status_is_reported_as_critical(monkeypatch):
    entry = certificate("", status="future_status")
    read = Mock(return_value=envelope([entry]))
    monkeypatch.setattr(ceph_certificate, "__salt__", {"ceph_certificates.list": read})
    event = ceph_certificate.beacon([])[0]
    assert event["tag"] == "critical"
    assert event["status"] == "future_status"


def test_read_failure_and_malformed_response_emit_nothing(monkeypatch):
    read = Mock(side_effect=[RuntimeError("secret"), {"status": 200, "data": {}}])
    monkeypatch.setattr(ceph_certificate, "__salt__", {"ceph_certificates.list": read})
    assert not ceph_certificate.beacon([])
    assert not ceph_certificate.beacon([])
    assert read.call_count == 2


def test_invalid_config_does_not_read(monkeypatch):
    read = Mock()
    monkeypatch.setattr(ceph_certificate, "__salt__", {"ceph_certificates.list": read})
    assert not ceph_certificate.beacon([{"critical_days": -1}])
    read.assert_not_called()
