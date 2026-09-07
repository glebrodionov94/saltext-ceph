"""Unit checks for safety-critical OSD live-test projections."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.integration.states import test_live_osd_states as live_osd

SERVICE_NAME = "osd.saltext-ci-live"
SERVICE_ID = "saltext-ci-live"
HOSTNAME = "ceph-node-1"
DEVICE_PATH = "/dev/sdc"


@pytest.mark.parametrize("nested_devices", (False, True))
def test_owned_osd_service_accepts_flat_and_nested_dashboard_specs(
    monkeypatch,
    nested_devices,
):
    current = {
        "service_name": SERVICE_NAME,
        "service_type": "osd",
        "service_id": SERVICE_ID,
        "placement": {"hosts": [HOSTNAME]},
    }
    devices = {"paths": [DEVICE_PATH]}
    if nested_devices:
        current["spec"] = {"data_devices": devices}
    else:
        current["data_devices"] = devices

    monkeypatch.setattr(live_osd, "_service", lambda *_args: current)
    monkeypatch.setattr(
        live_osd.service_resource,
        "get",
        lambda *_args: SimpleNamespace(data=current),
    )

    assert (
        live_osd._owned_osd_service(
            object(),
            SERVICE_NAME,
            SERVICE_ID,
            HOSTNAME,
            DEVICE_PATH,
        )
        is current
    )


def test_owned_osd_service_rejects_a_nested_device_mismatch(monkeypatch):
    current = {
        "service_name": SERVICE_NAME,
        "service_type": "osd",
        "service_id": SERVICE_ID,
        "placement": {"hosts": [HOSTNAME]},
        "spec": {"data_devices": {"paths": ["/dev/other"]}},
    }
    monkeypatch.setattr(live_osd, "_service", lambda *_args: current)
    monkeypatch.setattr(
        live_osd.service_resource,
        "get",
        lambda *_args: SimpleNamespace(data=current),
    )

    with pytest.raises(pytest.fail.Exception, match="exact host/device ownership"):
        live_osd._owned_osd_service(
            object(),
            SERVICE_NAME,
            SERVICE_ID,
            HOSTNAME,
            DEVICE_PATH,
        )


def test_cleanup_osd_absence_retries_transient_read_then_accepts_current(monkeypatch):
    absent = Mock(
        side_effect=[
            {"result": False, "changes": {}, "comment": "Ceph API HTTP 500: request failed."},
            {"result": True, "changes": {}, "comment": "OSD 7 is already absent."},
        ]
    )
    sleep = Mock()
    monkeypatch.setattr(live_osd.osd_state, "absent", absent)
    monkeypatch.setattr(live_osd.time, "monotonic", Mock(side_effect=[0.0, 0.0]))
    monkeypatch.setattr(live_osd.time, "sleep", sleep)

    result = live_osd._cleanup_osd_absence(7, retry_timeout=10.0, retry_interval=1.0)

    assert result["result"] is True
    assert not result["changes"]
    assert absent.call_count == 2
    absent.assert_called_with(
        7,
        confirm=True,
        preserve_id=False,
        force=False,
        profile="live",
        task_timeout=7200.0,
        task_interval=5.0,
    )
    sleep.assert_called_once_with(1.0)


def test_cleanup_osd_absence_accepts_changed_without_duplicate_delete(monkeypatch):
    absent = Mock(
        return_value={
            "result": True,
            "changes": {"old": {"id": 7}, "new": None},
            "comment": "OSD 7 was removed.",
        }
    )
    sleep = Mock()
    monkeypatch.setattr(live_osd.osd_state, "absent", absent)
    monkeypatch.setattr(live_osd.time, "monotonic", Mock(return_value=0.0))
    monkeypatch.setattr(live_osd.time, "sleep", sleep)

    result = live_osd._cleanup_osd_absence(7)

    assert result["result"] is True
    assert result["changes"]["new"] is None
    absent.assert_called_once()
    sleep.assert_not_called()


@pytest.mark.parametrize(
    "comment",
    (
        "OSD 7 is not currently safe to remove.",
        "Ceph API HTTP 400: invalid request.",
    ),
)
def test_cleanup_osd_absence_does_not_retry_non_transient_failure(monkeypatch, comment):
    absent = Mock(
        return_value={
            "result": False,
            "changes": {},
            "comment": comment,
        }
    )
    sleep = Mock()
    monkeypatch.setattr(live_osd.osd_state, "absent", absent)
    monkeypatch.setattr(live_osd.time, "monotonic", Mock(return_value=0.0))
    monkeypatch.setattr(live_osd.time, "sleep", sleep)

    with pytest.raises(pytest.fail.Exception, match=comment):
        live_osd._cleanup_osd_absence(7)

    absent.assert_called_once()
    sleep.assert_not_called()


def test_cleanup_osd_absence_stops_at_retry_deadline(monkeypatch):
    absent = Mock(
        return_value={"result": False, "changes": {}, "comment": "Ceph API HTTP 500: failed."}
    )
    sleep = Mock()
    monkeypatch.setattr(live_osd.osd_state, "absent", absent)
    monkeypatch.setattr(live_osd.time, "monotonic", Mock(side_effect=[0.0, 1.0]))
    monkeypatch.setattr(live_osd.time, "sleep", sleep)

    with pytest.raises(pytest.fail.Exception, match="cleanup retry deadline"):
        live_osd._cleanup_osd_absence(7, retry_timeout=0.5, retry_interval=0.1)

    absent.assert_called_once()
    sleep.assert_not_called()
