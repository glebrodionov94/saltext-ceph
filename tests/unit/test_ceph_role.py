"""Dashboard role controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_role as execution
from saltext.ceph.utils.ceph import role
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_role as wrapper


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


def test_list_and_get_use_role_resources(client):
    client.request.side_effect = [
        APIResponse(200, [{"name": "administrator", "system": True}]),
        APIResponse(200, {"name": "backup-manager", "system": False}),
    ]
    assert role.list_(client).data[0]["name"] == "administrator"
    client.request.assert_called_with("GET", "/api/role", api_version="1.0")
    assert role.get(client, "backup-manager").data["system"] is False
    client.request.assert_called_with("GET", "/api/role/backup-manager", api_version="1.0")


def test_create_sends_complete_permission_mapping(client):
    payload = {"pool": ["read"], "rbd-image": ["read", "create"]}
    client.request.return_value = APIResponse(
        201,
        {
            "name": "backup-manager",
            "description": "Backup operators",
            "scopes_permissions": payload,
            "system": False,
        },
    )
    result = role.create(client, "backup-manager", "Backup operators", payload)
    assert result.status == 201
    client.request.assert_called_once_with(
        "POST",
        "/api/role",
        api_version="1.0",
        data={
            "name": "backup-manager",
            "description": "Backup operators",
            "scopes_permissions": payload,
        },
    )


def test_update_delete_and_clone_use_member_routes(client):
    client.request.side_effect = [
        APIResponse(200, {"name": "backup-manager", "system": False}),
        APIResponse(204, None),
        APIResponse(201, {"name": "backup-copy", "system": False}),
    ]
    assert role.update(client, "backup-manager", None, {}).status == 200
    client.request.assert_called_with(
        "PUT",
        "/api/role/backup-manager",
        api_version="1.0",
        data={"description": None, "scopes_permissions": {}},
    )
    assert role.delete(client, "backup-manager", confirm=True).status == 204
    client.request.assert_called_with("DELETE", "/api/role/backup-manager", api_version="1.0")
    assert role.clone(client, "backup-manager", "backup-copy").status == 201
    client.request.assert_called_with(
        "POST",
        "/api/role/backup-manager/clone",
        api_version="1.0",
        data={"new_name": "backup-copy"},
    )


@pytest.mark.parametrize("name", [None, "", "bad/name", "bad role", ".hidden", "x" * 256])
def test_invalid_role_names_fail_before_http(client, name):
    with pytest.raises(ConfigurationError):
        role.get(client, name)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        [],
        "pool=read",
        {"pool": "read"},
        {"bad/scope": ["read"]},
        {"pool": ["execute"]},
        {"pool": ["read", "read"]},
        {"pool": [1]},
        {"pool": [[]]},
    ],
)
def test_invalid_scope_permissions_fail_before_http(client, value):
    with pytest.raises(ConfigurationError):
        role.create(client, "backup-manager", scopes_permissions=value)
    client.request.assert_not_called()


def test_empty_scope_and_permission_collections_are_supported(client):
    client.request.return_value = APIResponse(201, {"name": "empty", "system": False})
    role.create(client, "empty", scopes_permissions={"pool": []})
    assert client.request.call_args.kwargs["data"]["scopes_permissions"] == {"pool": []}


@pytest.mark.parametrize("payload", [None, {}, ["invalid"]])
def test_list_rejects_invalid_response_shape(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        role.list_(client)


@pytest.mark.parametrize("operation", [role.get, role.create, role.update, role.clone])
def test_mapping_operations_reject_invalid_response_shape(client, operation):
    client.request.return_value = APIResponse(200, [])
    args = {
        role.get: ("role",),
        role.create: ("role",),
        role.update: ("role",),
        role.clone: ("role", "copy"),
    }[operation]
    with pytest.raises(ProtocolError):
        operation(client, *args)
