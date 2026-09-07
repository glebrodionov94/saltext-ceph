"""RGW roles and current account Dashboard adapter tests."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rgw_iam as execution
from saltext.ceph.utils.ceph import rgw_iam
from saltext.ceph.utils.ceph import rgw_iam_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rgw_iam as wrapper


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
        api_parameters = list(inspect.signature(getattr(rgw_iam_api, name)).parameters.values())
        assert inspect.signature(getattr(execution, name)) == inspect.Signature(api_parameters[3:])


@pytest.mark.parametrize(
    "account_id,path",
    [
        (None, "/api/rgw/roles"),
        ("RGW12345678901234567", "/api/rgw/accounts/RGW12345678901234567/roles"),
    ],
)
def test_list_roles_selects_reef_or_current_route(client, account_id, path):
    client.request.return_value = APIResponse(200, [{"RoleName": "reader"}])
    rgw_iam.list_roles(client, account_id)
    client.request.assert_called_once_with("GET", path, api_version="1.0")


def test_get_role_is_account_scoped_and_encodes_name(client):
    rgw_iam.get_role(client, "RGW12345678901234567", "read+only")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/accounts/RGW12345678901234567/roles/read%2Bonly",
        api_version="1.0",
    )


def test_create_role_keeps_account_id_in_current_route_not_body(client):
    rgw_iam.create_role(
        client, "reader", "/teams/", '{"Version":"2012-10-17"}', "RGW12345678901234567"
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/rgw/accounts/RGW12345678901234567/roles",
        api_version="1.0",
        data={
            "role_name": "reader",
            "role_path": "/teams/",
            "role_assume_policy_doc": '{"Version":"2012-10-17"}',
        },
    )


def test_update_role_uses_collection_put(client):
    rgw_iam.update_role(client, "reader", "2")
    client.request.assert_called_once_with(
        "PUT",
        "/api/rgw/roles",
        api_version="1.0",
        data={"role_name": "reader", "max_session_duration": "2"},
    )


@pytest.mark.parametrize(
    "operation,args",
    [
        (rgw_iam.list_roles, ("not-an-account",)),
        (rgw_iam.create_role, ("bad role", "/teams/")),
        (rgw_iam.create_role, ("reader", "teams")),
        (rgw_iam.create_role, ("reader", "/teams/", "not-json")),
        (rgw_iam.create_role, ("reader", "/teams/", "[]")),
        (rgw_iam.update_role, ("reader", "forever")),
        (rgw_iam.update_role, ("reader", 13)),
    ],
)
def test_role_contract_validation_happens_before_http(client, operation, args):
    with pytest.raises(ConfigurationError):
        operation(client, *args)
    client.request.assert_not_called()


def test_role_deletion_requires_confirmation(client):
    with pytest.raises(ConfigurationError):
        rgw_iam.delete_role(client, "reader")
    client.request.assert_not_called()


def test_role_deletion_uses_release_selected_route(client):
    client.request.return_value = APIResponse(204, None)
    rgw_iam.delete_role(client, "reader", "RGW12345678901234567", confirm=True)
    client.request.assert_called_once_with(
        "DELETE", "/api/rgw/accounts/RGW12345678901234567/roles/reader", api_version="1.0"
    )


def test_create_account_uses_current_route_and_controller_names(client):
    client.request.return_value = APIResponse(201, {"id": "RGW12345678901234567"})
    rgw_iam.create_account(
        client,
        "team",
        tenant="tenant",
        email="ops@example.test",
        max_buckets=10,
        max_users="20",
        max_roles=30,
        max_groups=40,
        max_access_keys=5,
        daemon_name="rgw.a",
    )
    assert client.request.call_args.args == ("POST", "/api/rgw/accounts")
    assert client.request.call_args.kwargs["data"] == {
        "account_name": "team",
        "tenant": "tenant",
        "email": "ops@example.test",
        "daemon_name": "rgw.a",
        "max_buckets": 10,
        "max_users": 20,
        "max_roles": 30,
        "max_group": 40,
        "max_access_keys": 5,
    }


@pytest.mark.parametrize(
    "detailed,payload,params",
    [
        (False, ["RGW12345678901234567"], {}),
        (True, [{"id": "RGW12345678901234567"}], {"detailed": True}),
    ],
)
def test_list_accounts_omits_main_default_and_validates_shape(client, detailed, payload, params):
    client.request.return_value = APIResponse(200, payload)
    rgw_iam.list_accounts(client, detailed=detailed)
    client.request.assert_called_once_with(
        "GET", "/api/rgw/accounts", api_version="1.0", params=params
    )


@pytest.mark.parametrize(
    "detailed,payload", [(False, [{}]), (True, ["RGW12345678901234567"]), (False, {})]
)
def test_list_accounts_rejects_wrong_release_shape(client, detailed, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        rgw_iam.list_accounts(client, detailed=detailed)


def test_account_get_exists_and_update_routes(client):
    rgw_iam.get_account(client, "RGW12345678901234567", "rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/accounts/RGW12345678901234567",
        api_version="1.0",
        params={"daemon_name": "rgw.a"},
    )
    client.reset_mock()
    client.request.return_value = APIResponse(200, True)
    assert rgw_iam.account_exists(client, "team").data is True
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/accounts/exists",
        api_version="1.0",
        params={"account_name": "team"},
    )
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"id": "RGW12345678901234567"})
    rgw_iam.update_account(client, "RGW12345678901234567", "new-name", max_users=7)
    assert client.request.call_args.args == ("PUT", "/api/rgw/accounts/RGW12345678901234567")
    assert client.request.call_args.kwargs["data"] == {
        "account_name": "new-name",
        "max_users": 7,
    }


def test_account_exists_rejects_non_boolean(client):
    client.request.return_value = APIResponse(200, {"exists": True})
    with pytest.raises(ProtocolError):
        rgw_iam.account_exists(client, "team")


def test_delete_account_requires_confirmation_then_preserves_204(client):
    with pytest.raises(ConfigurationError):
        rgw_iam.delete_account(client, "RGW12345678901234567")
    client.request.assert_not_called()
    client.request.return_value = APIResponse(204, None)
    rgw_iam.delete_account(client, "RGW12345678901234567", confirm=True)
    client.request.assert_called_once_with(
        "DELETE", "/api/rgw/accounts/RGW12345678901234567", api_version="1.0", params={}
    )


def test_account_quota_preserves_size_strings_and_status_contract(client):
    rgw_iam.set_account_quota(client, "RGW12345678901234567", "account", "10G", "100000", True)
    client.request.assert_called_once_with(
        "PUT",
        "/api/rgw/accounts/RGW12345678901234567/quota",
        api_version="1.0",
        data={
            "quota_type": "account",
            "max_size": "10G",
            "max_objects": "100000",
            "enabled": True,
        },
    )
    client.reset_mock()
    rgw_iam.set_account_quota_status(client, "RGW12345678901234567", "bucket", "disable")
    client.request.assert_called_once_with(
        "PUT",
        "/api/rgw/accounts/RGW12345678901234567/quota/status",
        api_version="1.0",
        data={"quota_type": "bucket", "quota_status": "disable"},
    )


@pytest.mark.parametrize(
    "operation,args",
    [
        (rgw_iam.set_account_quota, ("RGW12345678901234567", "user", "10G", "1", True)),
        (rgw_iam.set_account_quota, ("RGW12345678901234567", "account", 10, "1", True)),
        (rgw_iam.set_account_quota_status, ("RGW12345678901234567", "account", "enabled")),
    ],
)
def test_account_quota_rejects_invalid_contract_before_http(client, operation, args):
    with pytest.raises(ConfigurationError):
        operation(client, *args)
    client.request.assert_not_called()
