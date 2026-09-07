"""Dashboard login-user operations and secret boundaries."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_dashboard_user as execution
from saltext.ceph.utils.ceph import dashboard_user
from saltext.ceph.utils.ceph import dashboard_user_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_dashboard_user as wrapper


@pytest.fixture
def client():
    return Mock()


def test_wrapper_exports_execution_functions_with_matching_signatures():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    assert names == {
        name
        for name, function in inspect.getmembers(wrapper, inspect.isfunction)
        if not name.startswith("_")
    }
    for name in names:
        assert inspect.signature(getattr(wrapper, name)) == inspect.signature(
            getattr(execution, name)
        )


def test_list_redacts_password_fields_defensively(client):
    client.request.return_value = APIResponse(
        200,
        [
            {
                "username": "operator",
                "password": "server-regression-secret",
                "roles": ["read-only"],
            }
        ],
    )
    result = dashboard_user.list_(client)
    assert result.data == [{"username": "operator", "roles": ["read-only"]}]
    assert "server-regression-secret" not in repr(result)
    client.request.assert_called_once_with("GET", "/api/user", api_version="1.0")


def test_get_encodes_email_style_username_and_redacts(client):
    client.request.return_value = APIResponse(
        200, {"username": "ops@example.com", "password": "private", "enabled": True}
    )
    result = dashboard_user.get(client, "ops@example.com")
    assert result.data == {"username": "ops@example.com", "enabled": True}
    client.request.assert_called_once_with("GET", "/api/user/ops%40example.com", api_version="1.0")


def test_create_uses_controller_field_names_and_never_returns_password(client):
    client.request.return_value = APIResponse(
        201, {"username": "operator", "password": "echoed", "roles": ["read-only"]}
    )
    result = dashboard_user.create(
        client,
        "operator",
        "new-secret",
        "Storage operator",
        "operator@example.com",
        ["read-only"],
        False,
        2_000_000_000,
        True,
    )
    assert result.data == {"username": "operator", "roles": ["read-only"]}
    client.request.assert_called_once_with(
        "POST",
        "/api/user",
        api_version="1.0",
        data={
            "username": "operator",
            "password": "new-secret",
            "name": "Storage operator",
            "email": "operator@example.com",
            "roles": ["read-only"],
            "enabled": False,
            "pwdExpirationDate": 2_000_000_000,
            "pwdUpdateRequired": True,
        },
    )


def test_update_uses_member_route_and_complete_mutable_fields(client):
    client.request.return_value = APIResponse(200, {"username": "operator"})
    dashboard_user.update(client, "operator", roles=[], enabled=True)
    client.request.assert_called_once_with(
        "PUT",
        "/api/user/operator",
        api_version="1.0",
        data={
            "password": None,
            "name": None,
            "email": None,
            "roles": [],
            "enabled": True,
            "pwdExpirationDate": None,
            "pwdUpdateRequired": False,
        },
    )


def test_delete_discards_server_body(client):
    client.request.return_value = APIResponse(204, {"password": "unexpected"})
    with pytest.raises(ConfigurationError, match="confirm=True"):
        dashboard_user.delete(client, "operator")
    client.request.assert_not_called()
    result = dashboard_user.delete(client, "operator", confirm=True)
    assert result.data == {"username": "operator"}
    assert "unexpected" not in repr(result.as_dict())
    client.request.assert_called_once_with("DELETE", "/api/user/operator", api_version="1.0")


def test_validate_password_whitelists_policy_metadata(client):
    client.request.return_value = APIResponse(
        201,
        {
            "valid": True,
            "credits": 25,
            "valuation": "Very strong",
            "password": "unexpected-echo",
        },
    )
    result = dashboard_user.validate_password_policy(client, "new-secret", "operator", "old-secret")
    assert result.data == {"valid": True, "credits": 25, "valuation": "Very strong"}
    assert "unexpected-echo" not in repr(result.as_dict())
    client.request.assert_called_once_with(
        "POST",
        "/api/user/validate_password",
        api_version="1.0",
        data={
            "password": "new-secret",
            "username": "operator",
            "old_password": "old-secret",
        },
    )


def test_change_password_discards_server_body(client):
    client.request.return_value = APIResponse(201, {"new_password": "unexpected"})
    result = dashboard_user.change_password(client, "operator", "old-secret", "new-secret")
    assert result.data == {"username": "operator"}
    assert "unexpected" not in repr(result.as_dict())
    client.request.assert_called_once_with(
        "POST",
        "/api/user/operator/change_password",
        api_version="1.0",
        data={"old_password": "old-secret", "new_password": "new-secret"},
    )


@pytest.mark.parametrize("username", [None, "", "bad/user", "bad user", ".hidden", "x" * 256])
def test_invalid_usernames_fail_before_http(client, username):
    with pytest.raises(ConfigurationError):
        dashboard_user.get(client, username)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "roles", ["read-only", ["bad role"], ["read-only", "read-only"], [1], [[]]]
)
def test_invalid_roles_fail_before_http(client, roles):
    with pytest.raises(ConfigurationError):
        dashboard_user.create(client, "operator", roles=roles)
    client.request.assert_not_called()


def test_role_references_may_include_ceph_cli_slash_names():
    assert dashboard_user.validate_roles(["rbd/pool-manager"]) == ["rbd/pool-manager"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"password": ""},
        {"password": "bad\x00password"},
        {"enabled": 1},
        {"pwd_expiration_date": True},
        {"pwd_expiration_date": -1},
        {"pwd_update_required": "yes"},
        {"name": 1},
    ],
)
def test_invalid_create_fields_fail_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        dashboard_user.create(client, "operator", **kwargs)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, {}, ["bad"]])
def test_list_rejects_invalid_protocol_shape(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        dashboard_user.list_(client)


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"valid": 1, "credits": 10, "valuation": "OK"}, {"valid": True}],
)
def test_validate_password_rejects_invalid_protocol_shape(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        dashboard_user.validate_password_policy(client, "secret")


def test_api_reads_password_file_and_strips_only_line_endings(tmp_path, monkeypatch):
    source = tmp_path / "password"
    source.write_text("private password\r\n", encoding="utf-8")
    client = Mock()
    client.request.return_value = APIResponse(
        201, {"username": "operator", "password": "private password"}
    )
    monkeypatch.setattr(dashboard_user_api, "_client", lambda *_args: client)
    result = dashboard_user_api.create({}, {}, {}, "operator", password_source=str(source))
    assert result["data"] == {"username": "operator"}
    assert "private password" not in repr(result)
    assert client.request.call_args.kwargs["data"]["password"] == "private password"


def test_api_change_password_reads_both_files_without_returning_them(tmp_path, monkeypatch):
    old_source = tmp_path / "old"
    new_source = tmp_path / "new"
    old_source.write_text("old-private\n", encoding="utf-8")
    new_source.write_text("new-private\n", encoding="utf-8")
    client = Mock()
    client.request.return_value = APIResponse(201, None)
    monkeypatch.setattr(dashboard_user_api, "_client", lambda *_args: client)
    result = dashboard_user_api.change_password(
        {}, {}, {}, "operator", str(old_source), str(new_source)
    )
    assert result["data"] == {"username": "operator"}
    assert "old-private" not in repr(result)
    assert "new-private" not in repr(result)
    assert client.request.call_args.kwargs["data"] == {
        "old_password": "old-private",
        "new_password": "new-private",
    }
