"""Dashboard login-user state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_dashboard_user as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def resource(**changes):
    value = {
        "username": "operator",
        "name": "Storage operator",
        "email": "operator@example.com",
        "roles": ["read-only"],
        "enabled": True,
        "pwdExpirationDate": None,
        "pwdUpdateRequired": True,
        "lastUpdate": 123,
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def declaration(password_source=None, **changes):
    values = {
        "password_source": password_source,
        "display_name": "Storage operator",
        "email": "operator@example.com",
        "roles": ["read-only"],
        "enabled": True,
        "pwd_expiration_date": None,
        "pwd_update_required": True,
    }
    values.update(changes)
    return values


def test_virtual_requires_execution_functions(monkeypatch):
    assert state.__virtual__()[0] is False
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_dashboard_user.list": Mock(),
            "ceph_dashboard_user.create": Mock(),
            "ceph_dashboard_user.update": Mock(),
            "ceph_dashboard_user.delete": Mock(),
        },
    )
    assert state.__virtual__() == "ceph_dashboard_user"


def test_present_noop_whitelists_public_fields_and_redacts_server_regression(monkeypatch):
    current = resource(password="do-not-return", token="also-private")
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_dashboard_user.list": Mock(return_value=envelope([current])),
            "ceph_dashboard_user.update": update,
        },
    )
    result = state.present("operator", **declaration())
    assert result["result"] is True
    assert not result["changes"]
    assert "do-not-return" not in repr(result)
    assert "also-private" not in repr(result)
    update.assert_not_called()


def test_present_plans_create_and_never_emits_password_or_source(tmp_path, monkeypatch):
    source = tmp_path / "bootstrap-password"
    source.write_text("highly-private\n", encoding="utf-8")
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_dashboard_user.list": Mock(return_value=envelope([])),
            "ceph_dashboard_user.create": create,
        },
    )
    result = state.present("operator", **declaration(str(source)))
    assert result["result"] is None
    assert "password" not in repr(result["changes"]).lower()
    assert "highly-private" not in repr(result)
    assert str(source) not in repr(result)
    create.assert_not_called()


def test_present_creates_from_source_waits_and_verifies(tmp_path, monkeypatch):
    source = tmp_path / "password"
    source.write_text("private-value\n", encoding="utf-8")
    create = Mock(
        return_value=envelope({"name": "user/create", "metadata": {"username": "operator"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_dashboard_user.list": Mock(side_effect=[envelope([]), envelope([resource()])]),
            "ceph_dashboard_user.create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.present("operator", **declaration(str(source)))
    assert result["result"] is True
    assert "private-value" not in repr(result)
    create.assert_called_once_with(
        "operator",
        password_source=str(source),
        name="Storage operator",
        email="operator@example.com",
        roles=["read-only"],
        enabled=True,
        pwd_expiration_date=None,
        pwd_update_required=True,
        profile="default",
    )
    wait.assert_called_once()


def test_existing_user_update_never_rotates_unverifiable_password(tmp_path, monkeypatch):
    source = tmp_path / "changed-password"
    source.write_text("new-private-value", encoding="utf-8")
    before = resource(name="Old name")
    update = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_dashboard_user.list": Mock(
                side_effect=[envelope([before]), envelope([resource()])]
            ),
            "ceph_dashboard_user.update": update,
        },
    )
    result = state.present("operator", **declaration(str(source)))
    assert result["result"] is True
    assert "new-private-value" not in repr(result)
    assert update.call_args.kwargs["password_source"] is None


def test_existing_user_does_not_require_create_only_source_to_remain(tmp_path, monkeypatch):
    missing = tmp_path / "removed-after-bootstrap"
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_dashboard_user.list": Mock(return_value=envelope([resource()]))},
    )
    result = state.present("operator", **declaration(str(missing)))
    assert result["result"] is True
    assert not result["changes"]


def test_invalid_password_source_fails_without_path_or_content(monkeypatch, tmp_path):
    source = tmp_path / "missing-sensitive-file"
    monkeypatch.setattr(state, "__opts__", {"test": True})
    read = Mock(return_value=envelope([]))
    monkeypatch.setattr(state, "__salt__", {"ceph_dashboard_user.list": read})
    result = state.present("operator", **declaration(str(source)))
    assert result["result"] is False
    assert str(source) not in result["comment"]
    assert not result["changes"]
    read.assert_called_once_with(profile="default")


def test_absent_test_mode_plans_without_confirmation_and_redacts(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    current = resource(password="server-private")
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_dashboard_user.list": Mock(return_value=envelope([current])),
            "ceph_dashboard_user.delete": delete,
        },
    )
    result = state.absent("operator")
    assert result["result"] is None
    assert "server-private" not in repr(result)
    delete.assert_not_called()


def test_absent_requires_confirmation_then_deletes_and_post_reads(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    list_ = Mock(side_effect=[envelope([resource()]), envelope([resource()]), envelope([])])
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_dashboard_user.list": list_, "ceph_dashboard_user.delete": delete},
    )
    assert state.absent("operator")["result"] is False
    delete.assert_not_called()
    result = state.absent("operator", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with("operator", confirm=True, profile="default")


def test_failed_post_read_is_reported_without_password_data(monkeypatch):
    before = resource(name="Old", password="hidden-before")
    after = resource(name="Still old", password="hidden-after")
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_dashboard_user.list": Mock(side_effect=[envelope([before]), envelope([after])]),
            "ceph_dashboard_user.update": Mock(return_value=envelope(status=200)),
        },
    )
    result = state.present("operator", **declaration())
    assert result["result"] is False
    assert "did not converge" in result["comment"]
    assert "hidden" not in repr(result)
