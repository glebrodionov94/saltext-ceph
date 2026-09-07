"""CephX controller operations and validation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.utils.ceph import users
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError


@pytest.fixture
def client():
    return Mock()


@pytest.fixture
def capabilities():
    return [
        {"entity": "mon", "cap": "allow r"},
        {"entity": "osd", "cap": "allow rw pool=backups"},
    ]


def test_list_always_redacts_key_material(client):
    client.request.return_value = APIResponse(
        200,
        [
            {"entity": "client.admin", "key": "server-regression-secret", "caps": {}},
            {"entity": "client.backup", "caps": {"mon": "allow r"}},
        ],
        {"content-type": "application/json"},
    )
    result = users.list_(client)
    client.request.assert_called_once_with("GET", "/api/cluster/user", api_version="1.0")
    assert result.data[0]["key"] == "***********"
    assert "server-regression-secret" not in repr(result)
    assert "key" not in result.data[1]


@pytest.mark.parametrize("payload", [{}, ["invalid"], None])
def test_list_rejects_invalid_protocol_shape(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        users.list_(client)


def test_get_uses_collection_and_returns_none_for_missing(client):
    client.request.return_value = APIResponse(
        200, [{"entity": "client.other", "key": "private", "caps": {}}]
    )
    result = users.get(client, "client.backup")
    assert result.status == 200
    assert result.data is None


def test_create_and_update_send_complete_capability_set(client, capabilities):
    client.request.side_effect = [APIResponse(201, "created"), APIResponse(200, "edited")]
    assert users.create(client, "client.backup", capabilities).status == 201
    client.request.assert_called_with(
        "POST",
        "/api/cluster/user",
        api_version="1.0",
        data={"user_entity": "client.backup", "capabilities": capabilities},
    )
    assert users.update(client, "client.backup", capabilities).status == 200
    client.request.assert_called_with(
        "PUT",
        "/api/cluster/user",
        api_version="1.0",
        data={"user_entity": "client.backup", "capabilities": capabilities},
    )


def test_delete_is_single_entity_for_cross_release_compatibility(client):
    client.request.return_value = APIResponse(204, None)
    assert users.delete(client, "client.backup", confirm=True).status == 204
    client.request.assert_called_once_with(
        "DELETE", "/api/cluster/user/client.backup", api_version="1.0"
    )


@pytest.mark.parametrize("confirm", [False, None, 1, "true"])
def test_delete_requires_explicit_boolean_confirmation(client, confirm):
    with pytest.raises(ConfigurationError):
        users.delete(client, "client.backup", confirm=confirm)
    client.request.assert_not_called()


def test_import_and_export_controller_contract(client):
    client.request.side_effect = [
        APIResponse(201, "imported"),
        APIResponse(201, "[client.backup]\n"),
    ]
    assert users.import_keyring(client, "[client.backup]\n key = private\n").data == "imported"
    client.request.assert_called_with(
        "POST",
        "/api/cluster/user",
        api_version="1.0",
        data={"import_data": "[client.backup]\n key = private\n"},
    )
    assert users.export_keyring(client, ["client.backup"]).data == "[client.backup]\n"
    client.request.assert_called_with(
        "POST",
        "/api/cluster/user/export",
        api_version="1.0",
        data={"entities": ["client.backup"]},
    )


@pytest.mark.parametrize(
    "entity",
    ["client", "client.", ".backup", "client/back", "client,admin", "client.back?x", " client.a"],
)
def test_invalid_entities_fail_before_http(client, entity):
    with pytest.raises(ConfigurationError):
        users.get(client, entity)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        "mon=allow r",
        [{}],
        [{"entity": "mon", "cap": ""}],
        [{"entity": "mon", "cap": "allow r", "extra": True}],
        [{"entity": "mon/bad", "cap": "allow r"}],
        [{"entity": "mon", "cap": "allow r\nprivate"}],
        [{"entity": "mon", "cap": "allow r"}, {"entity": "mon", "cap": "allow *"}],
    ],
)
def test_invalid_capabilities_fail_before_http(client, value):
    with pytest.raises(ConfigurationError):
        users.create(client, "client.backup", value)
    client.request.assert_not_called()


@pytest.mark.parametrize("entities", [None, [], "client.a", ["client.a", "client.a"]])
def test_invalid_export_entities_fail_before_http(client, entities):
    with pytest.raises(ConfigurationError):
        users.export_keyring(client, entities)
    client.request.assert_not_called()


def test_export_requires_text_response(client):
    client.request.return_value = APIResponse(201, {"key": "private"})
    with pytest.raises(ProtocolError):
        users.export_keyring(client, ["client.backup"])
