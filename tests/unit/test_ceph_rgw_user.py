"""RGW user Dashboard adapter tests across Reef and current Ceph."""

import inspect
from copy import deepcopy
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rgw_user as execution
from saltext.ceph.utils.ceph import rgw_user
from saltext.ceph.utils.ceph import rgw_user_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rgw_user as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, {})
    return client


def test_wrapper_matches_execution_module():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    for name in names:
        assert inspect.signature(getattr(execution, name)) == inspect.signature(
            getattr(wrapper, name)
        )
        api_parameters = list(inspect.signature(getattr(rgw_user_api, name)).parameters.values())
        assert inspect.signature(getattr(execution, name)) == inspect.Signature(api_parameters[3:])


def test_list_users_reef_default_omits_current_detailed_query(client):
    client.request.return_value = APIResponse(200, ["alice", "tenant$bob"])
    rgw_user.list_users(client, daemon_name="rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/user",
        api_version="1.0",
        params={"daemon_name": "rgw.a"},
    )


def test_detailed_user_list_is_current_only_and_redacts_keys(client):
    client.request.return_value = APIResponse(
        200,
        [{"uid": "alice", "keys": [{"access_key": "AK", "secret_key": "SK"}]}],
    )
    result = rgw_user.list_users(client, detailed=True)
    assert result.data[0]["keys"][0] == {
        "access_key": "***********",
        "secret_key": "***********",
    }
    client.request.assert_called_once_with(
        "GET", "/api/rgw/user", api_version="1.0", params={"detailed": True}
    )


@pytest.mark.parametrize(
    "detailed,payload", [(False, [{}]), (True, ["alice"]), (False, {}), (True, [None])]
)
def test_list_users_rejects_wrong_shape(client, detailed, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        rgw_user.list_users(client, detailed=detailed)


def test_get_user_encodes_tenant_uid_and_redacts_all_key_material(client):
    payload = {
        "uid": "tenant$alice",
        "keys": [{"access_key": "AK", "secret_key": "SK"}],
        "swift_keys": [{"user": "alice:swift", "secret_key": "swift"}],
    }
    client.request.return_value = APIResponse(200, payload)
    result = rgw_user.get_user(client, "tenant/alice", stats=False)
    assert result.data["keys"][0]["access_key"] == "***********"
    assert result.data["swift_keys"][0]["secret_key"] == "***********"
    assert result.data["redacted"] is True
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/user/tenant%2Falice",
        api_version="1.0",
        params={"stats": False},
    )


def test_get_user_requires_explicit_boolean_for_secret_opt_in(client):
    client.request.return_value = APIResponse(200, {"secret_key": "SK"})
    with pytest.raises(ConfigurationError):
        rgw_user.get_user(client, "alice", include_secrets="true")
    client.request.assert_not_called()


def test_get_user_secret_opt_in_returns_detached_payload(client):
    payload = {"secret_key": "SK"}
    client.request.return_value = APIResponse(200, payload)
    result = rgw_user.get_user(client, "alice", include_secrets=True)
    assert result.data == payload
    assert result.data is not payload


def test_get_emails_validates_string_list(client):
    client.request.return_value = APIResponse(200, ["a@example.test"])
    rgw_user.get_emails(client, "rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/user/get_emails",
        api_version="1.0",
        params={"daemon_name": "rgw.a"},
    )
    client.request.return_value = APIResponse(200, [None])
    with pytest.raises(ProtocolError):
        rgw_user.get_emails(client)


def test_create_user_omits_current_account_fields_for_reef_defaults(client):
    client.request.return_value = APIResponse(201, {"uid": "alice"})
    rgw_user.create_user(client, "alice", "Alice")
    assert client.request.call_args.kwargs["data"] == {
        "uid": "alice",
        "display_name": "Alice",
    }


def test_create_user_rejects_non_boolean_secret_opt_in_before_request(client):
    with pytest.raises(ConfigurationError):
        rgw_user.create_user(client, "alice", "Alice", include_secrets="true")
    client.request.assert_not_called()


def test_create_user_validates_account_policies_and_redacts_response(client):
    policies = {
        "attach": ["arn:aws:iam::aws:policy/ReadOnlyAccess"],
        "detach": ["arn:aws:iam::aws:policy/AdministratorAccess"],
    }
    original = deepcopy(policies)
    client.request.return_value = APIResponse(
        201, {"uid": "alice", "keys": [{"access_key": "AK", "secret_key": "SK"}]}
    )
    result = rgw_user.create_user(
        client,
        "alice",
        "Alice",
        generate_key=True,
        account_id="RGW1",
        account_root_user=True,
        account_policies=policies,
        confirm_policy_detach=True,
    )
    assert policies == original
    data = client.request.call_args.kwargs["data"]
    assert data["account_policies"] == policies
    assert data["account_root_user"] is True
    assert result.data["keys"][0]["secret_key"] == "***********"


@pytest.mark.parametrize(
    "policies",
    [[], {"put": []}, {"attach": "arn"}, {"attach": ["arn", "arn"]}],
)
def test_create_user_rejects_invalid_account_policy_mapping(client, policies):
    with pytest.raises(ConfigurationError):
        rgw_user.create_user(client, "alice", "Alice", account_policies=policies)
    client.request.assert_not_called()


def test_update_user_sends_only_supported_values(client):
    rgw_user.update_user(
        client,
        "tenant$alice",
        display_name="Alice B",
        suspended=True,
        account_root_user=False,
    )
    assert client.request.call_args.args == ("PUT", "/api/rgw/user/tenant%24alice")
    assert client.request.call_args.kwargs["data"] == {
        "display_name": "Alice B",
        "suspended": True,
    }


@pytest.mark.parametrize("confirm", [False, None, 1, "true"])
def test_delete_user_requires_literal_confirmation(client, confirm):
    with pytest.raises(ConfigurationError):
        rgw_user.delete_user(client, "alice", confirm=confirm)
    client.request.assert_not_called()


def test_delete_user_confirmed_preserves_no_content(client):
    client.request.return_value = APIResponse(204, None)
    result = rgw_user.delete_user(client, "tenant/alice", confirm=True)
    assert result.status == 204
    client.request.assert_called_once_with(
        "DELETE", "/api/rgw/user/tenant%2Falice", api_version="1.0", params={}
    )


def test_capability_create_and_guarded_delete_use_exact_contract(client):
    rgw_user.create_capability(client, "alice", "users", "read,write", "rgw.a")
    client.request.assert_called_once_with(
        "POST",
        "/api/rgw/user/alice/capability",
        api_version="1.0",
        data={"type": "users", "perm": "read,write", "daemon_name": "rgw.a"},
    )
    client.reset_mock()
    with pytest.raises(ConfigurationError):
        rgw_user.delete_capability(client, "alice", "users", "read")
    client.request.assert_not_called()
    client.request.return_value = APIResponse(204, None)
    rgw_user.delete_capability(client, "alice", "users", "read", confirm=True)
    assert client.request.call_args.args == (
        "DELETE",
        "/api/rgw/user/alice/capability",
    )


def test_create_key_redacts_generated_credentials_by_default(client):
    client.request.return_value = APIResponse(201, {"access_key": "AK", "secret_key": "SK"})
    result = rgw_user.create_key(client, "alice", generate_key=True)
    assert result.data == {
        "access_key": "***********",
        "secret_key": "***********",
        "redacted": True,
    }
    assert client.request.call_args.kwargs["data"] == {
        "key_type": "s3",
        "generate_key": True,
    }


def test_create_key_opt_in_returns_generated_credentials(client):
    client.request.return_value = APIResponse(201, {"access_key": "AK", "secret_key": "SK"})
    result = rgw_user.create_key(client, "alice", include_secrets=True)
    assert result.data["secret_key"] == "SK"


def test_delete_key_requires_confirmation_and_keeps_access_key_in_query(client):
    with pytest.raises(ConfigurationError):
        rgw_user.delete_key(client, "alice", access_key="AK")
    client.request.assert_not_called()
    client.request.return_value = APIResponse(204, None)
    rgw_user.delete_key(client, "alice", access_key="AK", confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        "/api/rgw/user/alice/key",
        api_version="1.0",
        params={"key_type": "s3", "access_key": "AK"},
    )


@pytest.mark.parametrize("key_type", ["rsa", "", None])
def test_key_type_is_validated_before_http(client, key_type):
    with pytest.raises(ConfigurationError):
        rgw_user.create_key(client, "alice", key_type=key_type)
    client.request.assert_not_called()


def test_quota_get_and_put_routes(client):
    client.request.return_value = APIResponse(200, {})
    rgw_user.get_quota(client, "alice", "rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/user/alice/quota",
        api_version="1.0",
        params={"daemon_name": "rgw.a"},
    )
    client.reset_mock()
    rgw_user.set_quota(client, "alice", "user", True, "1024", 100, "rgw.a")
    client.request.assert_called_once_with(
        "PUT",
        "/api/rgw/user/alice/quota",
        api_version="1.0",
        data={
            "quota_type": "user",
            "enabled": True,
            "max_size_kb": 1024,
            "max_objects": 100,
            "daemon_name": "rgw.a",
        },
    )


def test_user_quota_rejects_unknown_scope_before_http(client):
    with pytest.raises(ConfigurationError):
        rgw_user.set_quota(client, "alice", "account", True, -1, -1)
    client.request.assert_not_called()


def test_subuser_create_redacts_and_delete_is_guarded(client):
    client.request.return_value = APIResponse(201, {"secret_key": "swift-secret"})
    result = rgw_user.create_subuser(client, "alice", "alice:swift", "full", key_type="swift")
    assert result.data["secret_key"] == "***********"
    client.reset_mock()
    with pytest.raises(ConfigurationError):
        rgw_user.delete_subuser(client, "alice", "alice:swift")
    client.request.assert_not_called()
    client.request.return_value = APIResponse(204, None)
    rgw_user.delete_subuser(client, "alice", "alice:swift", confirm=True)
    assert client.request.call_args.args == (
        "DELETE",
        "/api/rgw/user/alice/subuser/alice%3Aswift",
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"access": "admin"},
        {"access": "full", "key_type": "rsa"},
    ],
)
def test_subuser_rejects_unknown_access_or_key_type(client, kwargs):
    with pytest.raises(ConfigurationError):
        rgw_user.create_subuser(client, "alice", "alice:swift", **kwargs)
    client.request.assert_not_called()


def test_current_user_rate_limit_routes(client):
    client.request.return_value = APIResponse(200, {})
    rgw_user.get_global_rate_limit(client)
    assert client.request.call_args.args == ("GET", "/api/rgw/user/ratelimit")
    client.reset_mock()
    rgw_user.get_rate_limit(client, "tenant$alice")
    assert client.request.call_args.args == (
        "GET",
        "/api/rgw/user/tenant%24alice/ratelimit",
    )
    client.reset_mock()
    rgw_user.set_rate_limit(client, "alice", True, 1, 2, 3, 4)
    assert client.request.call_args.kwargs["data"] == {
        "enabled": True,
        "max_read_ops": 1,
        "max_write_ops": 2,
        "max_read_bytes": 3,
        "max_write_bytes": 4,
    }


@pytest.mark.parametrize("field,value", [("stats", "true"), ("detailed", 1)])
def test_read_flags_require_real_booleans(client, field, value):
    with pytest.raises(ConfigurationError):
        if field == "stats":
            rgw_user.get_user(client, "alice", stats=value)
        else:
            rgw_user.list_users(client, detailed=value)
    client.request.assert_not_called()


def test_user_api_reads_credentials_from_files_and_redacts_result(client, monkeypatch, tmp_path):
    access_source = tmp_path / "access-key"
    secret_source = tmp_path / "secret-key"
    access_source.write_text("ACCESS\n", encoding="utf-8")
    secret_source.write_text("SECRET\n", encoding="utf-8")
    client.request.return_value = APIResponse(201, {"access_key": "ACCESS", "secret_key": "SECRET"})
    monkeypatch.setattr(rgw_user_api.ceph, "get_client", lambda *_: client)

    result = rgw_user_api.create_key(
        {},
        {},
        {},
        "alice",
        generate_key=False,
        access_key_source=str(access_source),
        secret_key_source=str(secret_source),
    )

    assert client.request.call_args.kwargs["data"]["access_key"] == "ACCESS"
    assert client.request.call_args.kwargs["data"]["secret_key"] == "SECRET"
    assert result["data"]["access_key"] == "***********"
    assert result["data"]["secret_key"] == "***********"


@pytest.mark.parametrize(
    "function", [execution.create_user, execution.create_key, execution.create_subuser]
)
def test_user_execution_signatures_expose_only_file_sources_for_credentials(function):
    parameters = inspect.signature(function).parameters
    assert "access_key" not in parameters
    assert "secret_key" not in parameters
    assert "access_key_source" in parameters
    assert "secret_key_source" in parameters


def test_user_key_delete_reads_access_key_from_file(client, monkeypatch, tmp_path):
    source = tmp_path / "access-key"
    source.write_text("ACCESS\n", encoding="utf-8")
    client.request.return_value = APIResponse(204, None)
    monkeypatch.setattr(rgw_user_api.ceph, "get_client", lambda *_: client)

    rgw_user_api.delete_key({}, {}, {}, "alice", access_key_source=str(source), confirm=True)

    assert client.request.call_args.kwargs["params"]["access_key"] == "ACCESS"
    assert "access_key" not in inspect.signature(execution.delete_key).parameters


def test_policy_detach_requires_confirmation(client):
    with pytest.raises(ConfigurationError):
        rgw_user.update_user(
            client,
            "alice",
            account_policies={"detach": ["arn:aws:iam::aws:policy/ReadOnlyAccess"]},
        )
    client.request.assert_not_called()
