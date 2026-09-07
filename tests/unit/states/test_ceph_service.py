"""Ceph ServiceSpec state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_service as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


SPEC = {
    "service_type": "rgw",
    "service_id": "realm.zone",
    "placement": {"label": "rgw", "count": 2},
}


def resource(spec=None):
    return {
        "service_name": "rgw.realm.zone",
        "status": {"running": 2},
        **(spec or SPEC),
    }


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def salt_for_reads(list_side_effect, get_side_effect=None):
    return {
        "ceph_service.list": Mock(side_effect=list_side_effect),
        "ceph_service.get": Mock(side_effect=get_side_effect or []),
    }


def test_present_is_idempotent_and_ignores_status(monkeypatch):
    salt = {
        "ceph_service.list": Mock(return_value=envelope([resource()])),
        "ceph_service.get": Mock(return_value=envelope(resource())),
        "ceph_service.update": Mock(),
    }
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present("rgw.realm.zone", SPEC)
    assert result["result"] is True
    salt["ceph_service.update"].assert_not_called()


def test_present_plans_create_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_service.list": Mock(return_value=envelope([])), "ceph_service.create": create},
    )
    result = state.present("rgw.realm.zone", SPEC)
    assert result["result"] is None
    create.assert_not_called()


def test_present_creates_waits_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([]), envelope([resource()])])
    get = Mock(return_value=envelope(resource()))
    create = Mock(
        return_value=envelope(
            {"name": "service/create", "metadata": {"service_name": "rgw.realm.zone"}},
            202,
        )
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_service.list": list_,
            "ceph_service.get": get,
            "ceph_service.create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.present("rgw.realm.zone", SPEC)
    assert result["result"] is True
    create.assert_called_once_with("rgw.realm.zone", SPEC, profile="default")
    wait.assert_called_once()


def test_present_updates_only_when_managed_spec_differs(monkeypatch):
    before = resource({**SPEC, "placement": {"label": "rgw", "count": 1}})
    list_ = Mock(side_effect=[envelope([before]), envelope([resource()])])
    get = Mock(side_effect=[envelope(before), envelope(resource())])
    update = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_service.list": list_, "ceph_service.get": get, "ceph_service.update": update},
    )
    result = state.present("rgw.realm.zone", SPEC)
    assert result["result"] is True
    update.assert_called_once()


def test_present_reports_failed_post_read(monkeypatch):
    before = resource({**SPEC, "placement": {"count": 1, "label": "rgw"}})
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_service.list": Mock(return_value=envelope([before])),
            "ceph_service.get": Mock(return_value=envelope(before)),
            "ceph_service.update": Mock(return_value=envelope(status=201)),
        },
    )
    result = state.present("rgw.realm.zone", SPEC)
    assert result["result"] is False
    assert "did not converge" in result["comment"]


def test_absent_requires_confirmation_for_live_delete(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_service.list": Mock(return_value=envelope([resource()])),
            "ceph_service.get": Mock(return_value=envelope(resource())),
            "ceph_service.delete": delete,
        },
    )
    assert state.absent("rgw.realm.zone")["result"] is False
    delete.assert_not_called()


def test_absent_deletes_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([resource()]), envelope([])])
    delete = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_service.list": list_,
            "ceph_service.get": Mock(return_value=envelope(resource())),
            "ceph_service.delete": delete,
        },
    )
    result = state.absent("rgw.realm.zone", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with("rgw.realm.zone", confirm=True, profile="default")


def test_absent_protects_core_services(monkeypatch):
    core = {"service_name": "mon", "service_type": "mon", "placement": {"count": 3}}
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_service.list": Mock(return_value=envelope([core])),
            "ceph_service.get": Mock(return_value=envelope(core)),
            "ceph_service.delete": Mock(),
        },
    )
    result = state.absent("mon", confirm=True)
    assert result["result"] is False
    assert "allow_core" in result["comment"]


def test_absent_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_service.list": Mock(return_value=envelope([])), "ceph_service.delete": delete},
    )
    assert state.absent("rgw.realm.zone")["result"] is True
    delete.assert_not_called()


def test_invalid_spec_fails_before_read(monkeypatch):
    list_ = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_service.list": list_})
    result = state.present("rgw.realm.zone", {"service_type": "rgw", "service_id": "other"})
    assert result["result"] is False
    list_.assert_not_called()
