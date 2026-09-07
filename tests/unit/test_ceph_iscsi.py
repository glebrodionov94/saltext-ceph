"""iSCSI Dashboard controller operations and validation."""

import inspect
from copy import deepcopy
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_iscsi as execution
from saltext.ceph.utils.ceph import iscsi
from saltext.ceph.utils.ceph import iscsi_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_iscsi as wrapper

TARGET_IQN = "iqn.2026-01.com.example:storage"
NEW_TARGET_IQN = "iqn.2026-01.com.example:storage-v2"
CLIENT_IQN = "iqn.2026-01.com.example:client-one"
SECOND_CLIENT_IQN = "iqn.2026-01.com.example:client-two"
EMPTY_AUTH = {
    "user": "",
    "password": "",
    "mutual_user": "",
    "mutual_password": "",
}


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(
        202, {"name": "iscsi/target/create", "metadata": {"target_iqn": TARGET_IQN}}
    )
    return client


@pytest.fixture
def target_config():
    return {
        "target_iqn": TARGET_IQN,
        "portals": [
            {"host": "gateway-a", "ip": "192.0.2.10"},
            {"host": "gateway-b", "ip": "2001:db8::10"},
        ],
        "target_controls": {"cmdsn_depth": 128, "immediate_data": True},
        "acl_enabled": True,
        "auth": EMPTY_AUTH.copy(),
        "disks": [
            {
                "pool": "rbd",
                "image": "disk-one",
                "backstore": "user:rbd",
                "controls": {"max_data_area_mb": 128},
                "lun": 0,
                "wwn": "64af6678-9694-4367-bacc-f8eb0baa0",
            },
            {
                "pool": "rbd",
                "image": "disk-two",
                "backstore": "user:rbd",
                "controls": {},
                "lun": 1,
            },
        ],
        "clients": [
            {
                "client_iqn": CLIENT_IQN,
                "luns": [{"pool": "rbd", "image": "disk-one"}],
                "auth": {
                    "user": "clientuser01",
                    "password": "clientpass001",
                    "mutual_user": "mutualuser01",
                    "mutual_password": "mutualpass001",
                },
            },
            {
                "client_iqn": SECOND_CLIENT_IQN,
                "luns": [],
                "auth": {},
            },
        ],
        "groups": [
            {
                "group_id": "group-one",
                "disks": [{"pool": "rbd", "image": "disk-two"}],
                "members": [SECOND_CLIENT_IQN],
            }
        ],
    }


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


def test_get_discovery_auth_uses_v1_and_redacts_secret_fields_by_default(client):
    payload = {
        "user": "discovery01",
        "password": "longpassword1",
        "mutual_user": "discovery02",
        "mutual_password": "longpassword2",
    }
    client.request.return_value = APIResponse(200, payload)
    result = iscsi.get_discovery_auth(client)
    assert result.data == {
        "user": "discovery01",
        "password": iscsi.REDACTED,
        "mutual_user": "discovery02",
        "mutual_password": iscsi.REDACTED,
        "redacted": True,
    }
    assert result.data is not payload
    client.request.assert_called_once_with("GET", "/api/iscsi/discoveryauth", api_version="1.0")


def test_get_discovery_auth_requires_explicit_opt_in_to_return_secrets(client):
    payload = {
        "user": "discovery01",
        "password": "longpassword1",
        "mutual_user": "discovery02",
        "mutual_password": "longpassword2",
    }
    client.request.return_value = APIResponse(200, payload)
    result = iscsi.get_discovery_auth(client, include_secrets=True)
    assert result.data == payload
    assert result.data is not payload


@pytest.mark.parametrize("include_secrets", [None, 1, "true"])
def test_get_discovery_auth_rejects_non_boolean_secret_opt_in(client, include_secrets):
    client.request.return_value = APIResponse(200, EMPTY_AUTH)
    with pytest.raises(ConfigurationError):
        iscsi.get_discovery_auth(client, include_secrets=include_secrets)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"user": "", "password": "", "mutual_user": ""},
        {**EMPTY_AUTH, "password": None},
    ],
)
def test_get_discovery_auth_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        iscsi.get_discovery_auth(client)


def test_set_discovery_auth_sends_json_body_used_by_dashboard_frontend(client):
    payload = {
        "user": "discovery01",
        "password": "longpassword1",
        "mutual_user": "discovery02",
        "mutual_password": "longpassword2",
    }
    client.request.return_value = APIResponse(200, payload)
    result = iscsi.set_discovery_auth(client, **payload)
    assert result.data == {
        "user": "discovery01",
        "password": iscsi.REDACTED,
        "mutual_user": "discovery02",
        "mutual_password": iscsi.REDACTED,
        "redacted": True,
    }
    client.request.assert_called_once_with(
        "PUT", "/api/iscsi/discoveryauth", api_version="1.0", data=payload
    )


def test_set_discovery_auth_accepts_four_empty_values_to_disable_auth(client):
    iscsi.set_discovery_auth(client)
    assert client.request.call_args.kwargs["data"] == EMPTY_AUTH


def test_salt_api_reads_discovery_passwords_from_local_files(client, tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    mutual = tmp_path / "mutual"
    primary.write_text("longpassword1\n", encoding="utf-8")
    mutual.write_text("longpassword2\r\n", encoding="utf-8")
    monkeypatch.setattr(iscsi_api, "_client", lambda *_args: client)
    client.request.return_value = APIResponse(200, EMPTY_AUTH)

    iscsi_api.set_discovery_auth(
        {},
        {},
        {},
        user="discovery01",
        password_source=str(primary),
        mutual_user="discovery02",
        mutual_password_source=str(mutual),
    )
    assert client.request.call_args.kwargs["data"] == {
        "user": "discovery01",
        "password": "longpassword1",
        "mutual_user": "discovery02",
        "mutual_password": "longpassword2",
    }


def test_salt_api_rejects_relative_discovery_secret_source_before_http(client, monkeypatch):
    monkeypatch.setattr(iscsi_api, "_client", lambda *_args: client)
    with pytest.raises(ConfigurationError, match="absolute regular file"):
        iscsi_api.set_discovery_auth(
            {}, {}, {}, user="discovery01", password_source="relative-secret"
        )
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"user": "short", "password": "longpassword1"},
        {"user": "discovery01", "password": "short"},
        {"user": "discovery 01", "password": "longpassword1"},
        {"user": "discovery01", "password": "bad password1"},
        {"mutual_user": "discovery02", "mutual_password": "longpassword2"},
        {"user": "discovery01", "password": "longpassword1", "mutual_user": "short"},
        {
            "user": "discovery01",
            "password": "longpassword1",
            "mutual_user": "discovery02",
            "mutual_password": "short",
        },
        {"user": None},
    ],
)
def test_set_discovery_auth_matches_controller_validation_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        iscsi.set_discovery_auth(client, **kwargs)
    client.request.assert_not_called()


def test_list_targets_is_unpaginated_and_uses_v1(client):
    client.request.return_value = APIResponse(200, [{"target_iqn": TARGET_IQN}])
    result = iscsi.list_targets(client)
    assert result.data == [{"target_iqn": TARGET_IQN}]
    client.request.assert_called_once_with("GET", "/api/iscsi/target", api_version="1.0")


@pytest.mark.parametrize("payload", [None, {}, [TARGET_IQN], [{}, None]])
def test_list_targets_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        iscsi.list_targets(client)


def test_get_target_encodes_iqn_path_and_validates_mapping(client):
    client.request.return_value = APIResponse(200, {"target_iqn": TARGET_IQN})
    result = iscsi.get_target(client, TARGET_IQN)
    assert result.data["target_iqn"] == TARGET_IQN
    client.request.assert_called_once_with(
        "GET",
        "/api/iscsi/target/iqn.2026-01.com.example%3Astorage",
        api_version="1.0",
    )


def test_target_reads_recursively_redact_client_and_target_chap_passwords(client):
    payload = {
        "target_iqn": TARGET_IQN,
        "auth": {**EMPTY_AUTH, "password": "longpassword1"},
        "clients": [{"auth": {**EMPTY_AUTH, "password": "clientpass001"}}],
    }
    client.request.return_value = APIResponse(200, payload)
    result = iscsi.get_target(client, TARGET_IQN)
    assert result.data["auth"]["password"] == iscsi.REDACTED
    assert result.data["clients"][0]["auth"]["password"] == iscsi.REDACTED
    assert result.data["redacted"] is True
    assert payload["auth"]["password"] == "longpassword1"

    visible = iscsi.get_target(client, TARGET_IQN, include_secrets=True)
    assert visible.data == payload
    assert visible.data is not payload


def test_get_target_rejects_invalid_response(client):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        iscsi.get_target(client, TARGET_IQN)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "storage",
        "iqn.2026-13.com.example:storage",
        "iqn.2026-01.com:storage",
        "iqn.2026-01.com.example:bad/name",
        "iqn.2026-01.com.example:bad_name",
        42,
    ],
)
def test_get_target_rejects_invalid_iqn_before_http(client, value):
    with pytest.raises(ConfigurationError):
        iscsi.get_target(client, value)
    client.request.assert_not_called()


def test_create_target_sends_complete_structured_payload_and_preserves_202(client, target_config):
    original = deepcopy(target_config)
    result = iscsi.create_target(client, **target_config)
    assert result.status == 202
    assert result.data["name"] == "iscsi/target/create"
    client.request.assert_called_once_with(
        "POST",
        "/api/iscsi/target",
        api_version="1.0",
        data={
            **target_config,
            "portals": [
                {"host": "gateway-a", "ip": "192.0.2.10"},
                {"host": "gateway-b", "ip": "2001:db8::10"},
            ],
            "clients": [
                target_config["clients"][0],
                {**target_config["clients"][1], "auth": EMPTY_AUTH},
            ],
        },
    )
    assert target_config == original


def test_create_target_supplies_controller_safe_defaults(client):
    iscsi.create_target(client, TARGET_IQN, [{"host": "gateway-a", "ip": "192.0.2.10"}])
    assert client.request.call_args.kwargs["data"] == {
        "target_iqn": TARGET_IQN,
        "target_controls": {},
        "acl_enabled": False,
        "auth": EMPTY_AUTH,
        "portals": [{"host": "gateway-a", "ip": "192.0.2.10"}],
        "disks": [],
        "clients": [],
        "groups": [],
    }


@pytest.mark.parametrize(
    "portals",
    [
        None,
        [],
        "gateway-a:192.0.2.10",
        [{"host": "gateway-a"}],
        [{"host": "bad host", "ip": "192.0.2.10"}],
        [{"host": "gateway-a", "ip": "example.com"}],
        [{"host": "gateway-a", "ip": "0.0.0.0"}],
        [{"host": "gateway-a", "ip": "224.0.0.1"}],
        [
            {"host": "gateway-a", "ip": "192.0.2.10"},
            {"host": "gateway-a", "ip": "192.0.2.10"},
        ],
    ],
)
def test_create_rejects_invalid_portals_before_http(client, portals):
    with pytest.raises(ConfigurationError):
        iscsi.create_target(client, TARGET_IQN, portals)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "disks",
    [
        "rbd/disk-one",
        [{"pool": "rbd", "image": "disk-one"}],
        [
            {
                "pool": "rbd",
                "image": "disk-one",
                "backstore": "bad backstore",
                "controls": {},
            }
        ],
        [
            {
                "pool": "bad/pool",
                "image": "disk-one",
                "backstore": "user:rbd",
                "controls": {},
            }
        ],
        [
            {
                "pool": "rbd",
                "image": "disk-one",
                "backstore": "user:rbd",
                "controls": {"bad control": 1},
            }
        ],
        [
            {
                "pool": "rbd",
                "image": "disk-one",
                "backstore": "user:rbd",
                "controls": {"cmdsn_depth": [128]},
            }
        ],
        [
            {
                "pool": "rbd",
                "image": "disk-one",
                "backstore": "user:rbd",
                "controls": {"ratio": float("nan")},
            }
        ],
        [
            {
                "pool": "rbd",
                "image": "disk-one",
                "backstore": "user:rbd",
                "controls": {},
                "lun": True,
            }
        ],
        [
            {
                "pool": "rbd",
                "image": "disk-one",
                "backstore": "user:rbd",
                "controls": {},
                "lun": 16384,
            }
        ],
    ],
)
def test_create_rejects_invalid_disk_shapes_before_http(client, disks):
    with pytest.raises(ConfigurationError):
        iscsi.create_target(
            client,
            TARGET_IQN,
            [{"host": "gateway-a", "ip": "192.0.2.10"}],
            disks=disks,
        )
    client.request.assert_not_called()


@pytest.mark.parametrize("duplicate_field", ["identity", "lun", "wwn"])
def test_create_rejects_duplicate_disk_identifiers(client, duplicate_field):
    first = {
        "pool": "rbd",
        "image": "disk-one",
        "backstore": "user:rbd",
        "controls": {},
        "lun": 0,
        "wwn": "wwn-one",
    }
    second = {
        "pool": "rbd",
        "image": "disk-two",
        "backstore": "user:rbd",
        "controls": {},
        "lun": 1,
        "wwn": "wwn-two",
    }
    if duplicate_field == "identity":
        second["image"] = "disk-one"
    else:
        second[duplicate_field] = first[duplicate_field]
    with pytest.raises(ConfigurationError):
        iscsi.create_target(
            client,
            TARGET_IQN,
            [{"host": "gateway-a", "ip": "192.0.2.10"}],
            disks=[first, second],
        )
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "clients",
    [
        [{"client_iqn": CLIENT_IQN, "luns": []}],
        [{"client_iqn": "invalid", "luns": [], "auth": {}}],
        [{"client_iqn": CLIENT_IQN, "luns": [], "auth": {"secret": "value"}}],
        [
            {
                "client_iqn": CLIENT_IQN,
                "luns": [{"pool": "rbd", "image": "missing"}],
                "auth": {},
            }
        ],
        [
            {"client_iqn": CLIENT_IQN, "luns": [], "auth": {}},
            {"client_iqn": CLIENT_IQN, "luns": [], "auth": {}},
        ],
        [
            {
                "client_iqn": CLIENT_IQN,
                "luns": [],
                "auth": {"user": "short", "password": "longpassword1"},
            }
        ],
    ],
)
def test_create_rejects_invalid_clients_before_http(client, clients):
    disk = {
        "pool": "rbd",
        "image": "disk-one",
        "backstore": "user:rbd",
        "controls": {},
    }
    with pytest.raises(ConfigurationError):
        iscsi.create_target(
            client,
            TARGET_IQN,
            [{"host": "gateway-a", "ip": "192.0.2.10"}],
            disks=[disk],
            clients=clients,
        )
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "groups",
    [
        [{"group_id": "group-one", "disks": []}],
        [{"group_id": "bad/group", "disks": [], "members": []}],
        [{"group_id": "group-one", "disks": [], "members": ["invalid"]}],
        [{"group_id": "group-one", "disks": [], "members": [SECOND_CLIENT_IQN]}],
        [
            {
                "group_id": "group-one",
                "disks": [{"pool": "rbd", "image": "missing"}],
                "members": [CLIENT_IQN],
            }
        ],
        [
            {"group_id": "group-one", "disks": [], "members": [CLIENT_IQN]},
            {"group_id": "group-two", "disks": [], "members": [CLIENT_IQN]},
        ],
    ],
)
def test_create_rejects_invalid_groups_before_http(client, groups):
    client_entry = {"client_iqn": CLIENT_IQN, "luns": [], "auth": {}}
    disk = {
        "pool": "rbd",
        "image": "disk-one",
        "backstore": "user:rbd",
        "controls": {},
    }
    with pytest.raises(ConfigurationError):
        iscsi.create_target(
            client,
            TARGET_IQN,
            [{"host": "gateway-a", "ip": "192.0.2.10"}],
            disks=[disk],
            clients=[client_entry],
            groups=groups,
        )
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "target_controls,acl_enabled",
    [
        ([], False),
        ({"bad control": 1}, False),
        ({"cmdsn_depth": None}, False),
        ({"cmdsn_depth": 128}, "false"),
    ],
)
def test_create_rejects_invalid_target_controls_or_acl(client, target_controls, acl_enabled):
    with pytest.raises(ConfigurationError):
        iscsi.create_target(
            client,
            TARGET_IQN,
            [{"host": "gateway-a", "ip": "192.0.2.10"}],
            target_controls=target_controls,
            acl_enabled=acl_enabled,
        )
    client.request.assert_not_called()


def test_update_requires_confirmation_before_validation_or_http(client):
    with pytest.raises(ConfigurationError):
        iscsi.update_target(
            client,
            TARGET_IQN,
            [{"host": "gateway-a", "ip": "192.0.2.10"}],
        )
    client.request.assert_not_called()


@pytest.mark.parametrize("confirm", [None, 1, "true"])
def test_update_requires_boolean_confirmation(client, confirm):
    with pytest.raises(ConfigurationError):
        iscsi.update_target(
            client,
            TARGET_IQN,
            [{"host": "gateway-a", "ip": "192.0.2.10"}],
            confirm=confirm,
        )
    client.request.assert_not_called()


def test_update_uses_full_replacement_body_and_can_rename_target(client, target_config):
    target_iqn = target_config.pop("target_iqn")
    result = iscsi.update_target(
        client,
        target_iqn,
        new_target_iqn=NEW_TARGET_IQN,
        confirm=True,
        **target_config,
    )
    assert result.status == 202
    call = client.request.call_args
    assert call.args == (
        "PUT",
        "/api/iscsi/target/iqn.2026-01.com.example%3Astorage",
    )
    assert call.kwargs["api_version"] == "1.0"
    assert call.kwargs["data"]["new_target_iqn"] == NEW_TARGET_IQN
    assert "target_iqn" not in call.kwargs["data"]


def test_update_defaults_new_iqn_to_existing_identity(client):
    iscsi.update_target(
        client,
        TARGET_IQN,
        [{"host": "gateway-a", "ip": "192.0.2.10"}],
        confirm=True,
    )
    assert client.request.call_args.kwargs["data"]["new_target_iqn"] == TARGET_IQN


def test_delete_requires_confirmation_before_http(client):
    with pytest.raises(ConfigurationError):
        iscsi.delete_target(client, TARGET_IQN)
    client.request.assert_not_called()


@pytest.mark.parametrize("confirm", [None, 1, "true"])
def test_delete_requires_boolean_confirmation(client, confirm):
    with pytest.raises(ConfigurationError):
        iscsi.delete_target(client, TARGET_IQN, confirm=confirm)
    client.request.assert_not_called()


def test_delete_uses_v1_and_preserves_202_task_response(client):
    client.request.return_value = APIResponse(
        202, {"name": "iscsi/target/delete", "metadata": {"target_iqn": TARGET_IQN}}
    )
    result = iscsi.delete_target(client, TARGET_IQN, confirm=True)
    assert result.status == 202
    assert result.data["name"] == "iscsi/target/delete"
    client.request.assert_called_once_with(
        "DELETE",
        "/api/iscsi/target/iqn.2026-01.com.example%3Astorage",
        api_version="1.0",
    )
