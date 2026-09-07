"""RGW multisite public Dashboard adapter tests."""

import inspect
from copy import deepcopy
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rgw_multisite as execution
from saltext.ceph.utils.ceph import rgw_multisite
from saltext.ceph.utils.ceph import rgw_multisite_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rgw_multisite as wrapper


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
        api_parameters = list(
            inspect.signature(getattr(rgw_multisite_api, name)).parameters.values()
        )
        assert inspect.signature(getattr(execution, name)) == inspect.Signature(api_parameters[3:])


def test_sync_status_and_policy_use_current_public_routes(client):
    rgw_multisite.get_sync_status(client, "rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/multisite/sync_status",
        api_version="1.0",
        params={"daemon_name": "rgw.a"},
    )
    client.reset_mock()
    rgw_multisite.get_sync_policy(client, "data", "zg1", True, "rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/multisite/sync-policy",
        api_version="1.0",
        params={
            "bucket_name": "data",
            "zonegroup_name": "zg1",
            "all_policy": True,
            "daemon_name": "rgw.a",
        },
    )


def test_mutation_preserves_dashboard_task_accepted_response(client):
    payload = {"name": "rgw/multisite/sync-policy-group/g1", "metadata": {"group_id": "g1"}}
    client.request.return_value = APIResponse(202, payload, {"content-type": "application/json"})

    result = rgw_multisite.create_sync_policy_group(client, "g1", "enabled")

    assert result.status == 202
    assert result.data == payload
    assert result.headers == {"content-type": "application/json"}


def test_sync_policy_group_get_create_update_routes(client):
    rgw_multisite.get_sync_policy_group(client, "group/one", "data", "rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/multisite/sync-policy-group/group%2Fone",
        api_version="1.0",
        params={"bucket_name": "data", "daemon_name": "rgw.a"},
    )
    client.reset_mock()
    rgw_multisite.create_sync_policy_group(client, "g1", "enabled")
    assert client.request.call_args.args == (
        "POST",
        "/api/rgw/multisite/sync-policy-group",
    )
    assert client.request.call_args.kwargs["data"]["group_id"] == "g1"
    client.reset_mock()
    rgw_multisite.update_sync_policy_group(client, "g1", "forbidden")
    assert client.request.call_args.args == (
        "PUT",
        "/api/rgw/multisite/sync-policy-group",
    )


@pytest.mark.parametrize(
    "operation",
    [rgw_multisite.create_sync_policy_group, rgw_multisite.update_sync_policy_group],
)
def test_sync_policy_group_rejects_unknown_status(client, operation):
    with pytest.raises(ConfigurationError):
        operation(client, "g1", "paused")
    client.request.assert_not_called()


def test_sync_policy_group_confirmed_delete_uses_resource_path(client):
    client.request.return_value = APIResponse(204, None)
    rgw_multisite.delete_sync_policy_group(client, "group/one", confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        "/api/rgw/multisite/sync-policy-group/group%2Fone",
        api_version="1.0",
        params={"bucket_name": "", "daemon_name": ""},
    )


def test_directional_sync_flow_body_and_guarded_delete_paths(client):
    rgw_multisite.create_sync_flow(client, "flow one", "directional", "g1", "zone-a", "zone-b")
    assert client.request.call_args.args == ("PUT", "/api/rgw/multisite/sync-flow")
    assert client.request.call_args.kwargs["data"]["source_zone"] == "zone-a"
    client.reset_mock()
    with pytest.raises(ConfigurationError):
        rgw_multisite.delete_sync_flow(client, "flow one", "directional", "g1", "zone-a", "zone-b")
    client.request.assert_not_called()
    client.request.return_value = APIResponse(204, None)
    rgw_multisite.delete_sync_flow(
        client,
        "flow one",
        "directional",
        "g1",
        "zone-a",
        "zone-b",
        confirm=True,
    )
    assert client.request.call_args.args == (
        "DELETE",
        "/api/rgw/multisite/sync-flow/flow%20one/directional/g1",
    )


@pytest.mark.parametrize(
    "flow_type,source,destination,zones",
    [
        ("fanout", "zone-a", "zone-b", None),
        ("directional", None, "zone-b", None),
    ],
)
def test_sync_flow_rejects_invalid_type_or_incomplete_direction(
    client, flow_type, source, destination, zones
):
    with pytest.raises(ConfigurationError):
        rgw_multisite.create_sync_flow(client, "f1", flow_type, "g1", source, destination, zones)
    client.request.assert_not_called()


def test_symmetrical_sync_flow_requires_exact_zone_change_mapping(client):
    changes = {"added": ["zone-a", "*"], "removed": ["zone-b"]}
    original = deepcopy(changes)
    rgw_multisite.create_sync_flow(
        client, "f1", "symmetrical", "g1", zones=changes, confirm_remove=True
    )
    assert changes == original
    assert client.request.call_args.kwargs["data"]["zones"] == changes
    client.reset_mock()
    for bad in (None, {"added": ["zone-a"]}, {"added": [], "removed": "zone-b"}):
        with pytest.raises(ConfigurationError):
            rgw_multisite.create_sync_flow(client, "f1", "symmetrical", "g1", zones=bad)
    client.request.assert_not_called()


def test_sync_pipe_uses_structured_change_mappings(client):
    added = {"added": ["zone-a"], "removed": []}
    removed = {"added": [], "removed": ["zone-b"]}
    rgw_multisite.create_sync_pipe(
        client,
        "g1",
        "pipe/one",
        added,
        removed,
        source_bucket="source",
        destination_bucket="destination",
        user="alice",
        mode="user",
        confirm_remove=True,
    )
    data = client.request.call_args.kwargs["data"]
    assert data["source_zones"] == added
    assert data["destination_zones"] == removed
    client.reset_mock()
    client.request.return_value = APIResponse(204, None)
    rgw_multisite.delete_sync_pipe(
        client,
        "g1",
        "pipe/one",
        ["zone-a"],
        ["zone-b"],
        confirm=True,
    )
    assert client.request.call_args.args == (
        "DELETE",
        "/api/rgw/multisite/sync-pipe/g1/pipe%2Fone",
    )


@pytest.mark.parametrize(
    "operation,args",
    [
        (rgw_multisite.delete_sync_policy_group, ("g1",)),
        (
            rgw_multisite.delete_sync_flow,
            ("f1", "directional", "g1", "zone-a", "zone-b"),
        ),
        (rgw_multisite.delete_sync_pipe, ("g1", "p1")),
        (rgw_multisite.delete_realm, ("r1",)),
        (rgw_multisite.delete_zonegroup, ("zg1",)),
        (rgw_multisite.delete_zonegroup_storage_class, ("default", "COLD")),
        (rgw_multisite.delete_zone, ("z1",)),
    ],
)
def test_all_multisite_deletes_require_confirmation(client, operation, args):
    with pytest.raises(ConfigurationError):
        operation(client, *args)
    client.request.assert_not_called()


def test_realm_crud_and_current_replicable_query(client):
    rgw_multisite.create_realm(client, "realm one", True)
    client.request.assert_called_once_with(
        "POST",
        "/api/rgw/realm",
        api_version="1.0",
        data={"realm_name": "realm one", "default": True},
    )
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"realms": ["realm one"]})
    rgw_multisite.list_realms(client)
    assert client.request.call_args.kwargs["params"] == {}
    client.reset_mock()
    client.request.return_value = APIResponse(200, [{"name": "realm one"}])
    rgw_multisite.list_realms(client, replicable=True)
    assert client.request.call_args.kwargs["params"] == {"replicable": True}
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"name": "realm one"})
    rgw_multisite.get_realm(client, "realm one")
    assert client.request.call_args.args == (
        "GET",
        "/api/rgw/realm/realm%20one",
    )
    client.reset_mock()
    rgw_multisite.update_realm(client, "r1", "r2", True)
    assert client.request.call_args.kwargs["data"] == {
        "new_realm_name": "r2",
        "default": True,
    }


def test_realm_topology_route_validates_mapping(client):
    client.request.return_value = APIResponse(200, {"realms": []})
    rgw_multisite.get_all_realms_info(client)
    client.request.assert_called_once_with(
        "GET", "/api/rgw/realm/get_all_realms_info", api_version="1.0"
    )
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        rgw_multisite.get_all_realms_info(client)


def test_realm_tokens_are_wholly_hidden_without_opt_in(client):
    tokens = [{"realm": "r1", "token": "base64-secret"}]
    client.request.return_value = APIResponse(200, tokens)
    redacted = rgw_multisite.get_realm_tokens(client)
    assert redacted.data == {
        "redacted": True,
        "count": 1,
        "value": "***********",
    }
    visible = rgw_multisite.get_realm_tokens(client, include_secrets=True)
    assert visible.data == tokens
    assert visible.data is not tokens


@pytest.mark.parametrize(
    "placement",
    ["2 host-a host-b", {"count": 2, "hosts": ["host-a", "host-b"]}],
)
def test_import_realm_token_accepts_documented_placement_shapes(client, placement):
    client.request.return_value = APIResponse(200, {"access_key": "AK", "secret_key": "SK"})
    result = rgw_multisite.import_realm_token(
        client, "token/value==", "zone-b", "8080", placement, "cloud-transition"
    )
    assert result.data["secret_key"] == "***********"
    assert client.request.call_args.kwargs["data"]["placement_spec"] == placement
    assert client.request.call_args.kwargs["data"]["port"] == 8080


def test_import_realm_token_rejects_non_string_or_mapping_placement(client):
    with pytest.raises(ConfigurationError):
        rgw_multisite.import_realm_token(client, "token", "zone-b", 8080, ["host-a"])
    client.request.assert_not_called()


def test_confirmed_realm_delete_preserves_empty_response(client):
    client.request.return_value = APIResponse(204, None)
    result = rgw_multisite.delete_realm(client, "realm/one", confirm=True)
    assert result.status == 204
    client.request.assert_called_once_with(
        "DELETE", "/api/rgw/realm/realm%2Fone", api_version="1.0"
    )


def test_zonegroup_crud_uses_structured_lists(client):
    rgw_multisite.create_zonegroup(
        client, "r1", "zg1", default=True, master=False, zonegroup_endpoints="https://zg"
    )
    assert client.request.call_args.args == ("POST", "/api/rgw/zonegroup")
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"zonegroups": ["zg1"]})
    rgw_multisite.list_zonegroups(client)
    client.request.assert_called_once_with("GET", "/api/rgw/zonegroup", api_version="1.0")
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"name": "zg1"})
    rgw_multisite.get_zonegroup(client, "zg1")
    assert client.request.call_args.args == ("GET", "/api/rgw/zonegroup/zg1")
    client.reset_mock()
    rgw_multisite.update_zonegroup(
        client,
        "zg1",
        "r1",
        "zg2",
        add_zones=["zone-a"],
        remove_zones=["zone-b"],
        placement_targets=[{"name": "default-placement"}],
        confirm_remove=True,
    )
    data = client.request.call_args.kwargs["data"]
    assert data["add_zones"] == ["zone-a"]
    assert data["placement_targets"] == [{"name": "default-placement"}]


def test_zonegroup_topology_requires_mapping(client):
    client.request.return_value = APIResponse(200, {"zonegroups": []})
    rgw_multisite.get_all_zonegroups_info(client)
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        rgw_multisite.get_all_zonegroups_info(client)


def test_delete_zonegroup_sends_pool_guard_fields(client):
    client.request.return_value = APIResponse(204, None)
    rgw_multisite.delete_zonegroup(
        client,
        "zg1",
        delete_pools=True,
        pools=["rgw.meta", "rgw.data"],
        realm_name="r1",
        confirm=True,
    )
    client.request.assert_called_once_with(
        "DELETE",
        "/api/rgw/zonegroup/zg1",
        api_version="1.0",
        params={
            "delete_pools": True,
            "pools": ["rgw.meta", "rgw.data"],
            "realm_name": "r1",
        },
    )


def test_current_zonegroup_storage_class_routes(client):
    rgw_multisite.get_placement_target(client, "default/placement")
    assert client.request.call_args.args == (
        "GET",
        "/api/rgw/zonegroup/get_placement_target_by_placement_id/default%2Fplacement",
    )
    client.reset_mock()
    rgw_multisite.set_zonegroup_storage_classes(
        client, "zg1", [{"placement_target": "default", "storage_class": "COLD"}]
    )
    assert client.request.call_args.args == (
        "POST",
        "/api/rgw/zonegroup/storage-class",
    )
    client.reset_mock()
    rgw_multisite.set_zonegroup_storage_classes(client, "zg1", [], edit=True)
    assert client.request.call_args.args == (
        "PUT",
        "/api/rgw/zonegroup/storage-class",
    )
    client.reset_mock()
    client.request.return_value = APIResponse(204, None)
    rgw_multisite.delete_zonegroup_storage_class(client, "default", "COLD", "zone-a", confirm=True)
    assert client.request.call_args.args == (
        "DELETE",
        "/api/rgw/zonegroup/storage-class/default/COLD",
    )


def test_zone_create_redacts_system_credentials_and_omits_main_fields(client):
    client.request.return_value = APIResponse(
        201,
        {"name": "zone-a", "system_key": {"access_key": "AK", "secret_key": "SK"}},
    )
    result = rgw_multisite.create_zone(client, "zone-a", "zg1", access_key="AK", secret_key="SK")
    data = client.request.call_args.kwargs["data"]
    assert "tier_type" not in data
    assert "sync_from" not in data
    assert result.data["system_key"]["secret_key"] == "***********"


def test_zone_create_rejects_non_boolean_secret_opt_in_before_request(client):
    with pytest.raises(ConfigurationError):
        rgw_multisite.create_zone(client, "zone-a", include_secrets="true")
    client.request.assert_not_called()


def test_zone_create_current_tier_and_sync_fields_are_opt_in(client):
    rgw_multisite.create_zone(
        client,
        "zone-b",
        "zg1",
        tier_type="cloud-transition",
        sync_from="zone-a",
        sync_from_all=False,
    )
    data = client.request.call_args.kwargs["data"]
    assert data["tier_type"] == "cloud-transition"
    assert data["sync_from_all"] is False


def test_zone_list_get_and_topology_redact_keys_by_default(client):
    client.request.return_value = APIResponse(
        200,
        {
            "zones": ["z1"],
            "system_key": {"access_key": "AK", "secret_key": "SK"},
        },
    )
    assert rgw_multisite.list_zones(client).data["system_key"]["secret_key"] == "***********"
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"name": "z1", "secret_key": "SK"})
    assert rgw_multisite.get_zone(client, "z1").data["secret_key"] == "***********"
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"zones": [], "access_key": "AK"})
    assert rgw_multisite.get_all_zones_info(client).data["access_key"] == "***********"


def test_update_zone_preserves_exact_reef_body_and_optional_current_fields(client):
    rgw_multisite.update_zone(
        client,
        "z1",
        "z2",
        "zg1",
        placement_target="default",
        data_pool="rgw.data",
        index_pool="rgw.index",
        tier_type="cloud-transition",
        sync_from="z0",
        sync_from_all=True,
    )
    data = client.request.call_args.kwargs["data"]
    assert data["new_zone_name"] == "z2"
    assert data["data_pool"] == "rgw.data"
    assert data["sync_from_all"] is True
    assert "zone_name" not in data


def test_delete_zone_sends_current_realm_and_pool_fields(client):
    client.request.return_value = APIResponse(204, None)
    rgw_multisite.delete_zone(
        client,
        "z1",
        delete_pools=True,
        pools=["rgw.data"],
        zonegroup_name="zg1",
        realm_name="r1",
        confirm=True,
    )
    assert client.request.call_args.kwargs["params"] == {
        "delete_pools": True,
        "pools": ["rgw.data"],
        "zonegroup_name": "zg1",
        "realm_name": "r1",
    }


def test_zone_pool_system_user_user_list_and_storage_class_routes(client):
    client.request.return_value = APIResponse(200, [{"poolname": "rgw.data"}])
    rgw_multisite.get_pool_names(client)
    assert client.request.call_args.args == ("GET", "/api/rgw/zone/get_pool_names")
    client.reset_mock()
    client.request.return_value = APIResponse(200, {"access_key": "AK", "secret_key": "SK"})
    result = rgw_multisite.create_system_user(client, "zone-user", "z1")
    assert result.data["secret_key"] == "***********"
    assert client.request.call_args.kwargs["data"] == {
        "userName": "zone-user",
        "zoneName": "z1",
    }
    client.reset_mock()
    client.request.return_value = APIResponse(200, ["alice"])
    rgw_multisite.get_user_list(client, "z1", "r1")
    assert client.request.call_args.kwargs["params"] == {
        "zoneName": "z1",
        "realmName": "r1",
    }
    client.reset_mock()
    rgw_multisite.set_zone_storage_class(
        client, "z1", "default", "COLD", "rgw.cold", "zstd", edit=True
    )
    assert client.request.call_args.args == (
        "PUT",
        "/api/rgw/zone/storage-class",
    )


@pytest.mark.parametrize(
    "operation,payload",
    [
        (rgw_multisite.get_pool_names, ["rgw.data"]),
        (rgw_multisite.get_user_list, [{"uid": "alice"}]),
    ],
)
def test_zone_pool_and_user_lists_reject_wrong_item_shapes(client, operation, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        operation(client)


@pytest.mark.parametrize(
    "operation,args",
    [
        (rgw_multisite.get_sync_policy, ("", "", "true")),
        (rgw_multisite.create_realm, ("r1", "true")),
        (rgw_multisite.create_zone, ("z1", None, "false")),
        (rgw_multisite.delete_zone, ("z1", "true", [], None, None, True)),
    ],
)
def test_multisite_boolean_fields_are_not_string_coerced(client, operation, args):
    with pytest.raises(ConfigurationError):
        operation(client, *args)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "operation,args",
    [
        (
            rgw_multisite.create_sync_flow,
            ("f1", "symmetrical", "g1", None, None, {"added": [], "removed": ["z1"]}),
        ),
        (
            rgw_multisite.create_sync_pipe,
            (
                "g1",
                "p1",
                {"added": [], "removed": ["z1"]},
                {"added": ["z2"], "removed": []},
            ),
        ),
        (rgw_multisite.update_zonegroup, ("zg1", "r1", "zg1", False, False, "", [], ["z1"])),
    ],
)
def test_change_payload_removals_require_confirmation(client, operation, args):
    with pytest.raises(ConfigurationError):
        operation(client, *args)
    client.request.assert_not_called()


def test_multisite_api_reads_realm_token_from_file(client, monkeypatch, tmp_path):
    source = tmp_path / "realm-token"
    source.write_text("token/value==\n", encoding="utf-8")
    monkeypatch.setattr(rgw_multisite_api.ceph, "get_client", lambda *_: client)

    rgw_multisite_api.import_realm_token(
        {}, {}, {}, str(source), "zone-b", 8080, placement_spec="1 host-a"
    )

    assert client.request.call_args.kwargs["data"]["realm_token"] == "token/value=="
    parameters = inspect.signature(execution.import_realm_token).parameters
    assert "realm_token" not in parameters
    assert "realm_token_source" in parameters


@pytest.mark.parametrize("operation", ["create", "update"])
def test_multisite_api_reads_zone_keys_from_files(client, monkeypatch, tmp_path, operation):
    access_source = tmp_path / "access-key"
    secret_source = tmp_path / "secret-key"
    access_source.write_text("ACCESS\n", encoding="utf-8")
    secret_source.write_text("SECRET\n", encoding="utf-8")
    monkeypatch.setattr(rgw_multisite_api.ceph, "get_client", lambda *_: client)

    if operation == "create":
        rgw_multisite_api.create_zone(
            {},
            {},
            {},
            "z1",
            access_key_source=str(access_source),
            secret_key_source=str(secret_source),
        )
        function = execution.create_zone
    else:
        rgw_multisite_api.update_zone(
            {},
            {},
            {},
            "z1",
            "z1",
            "zg1",
            access_key_source=str(access_source),
            secret_key_source=str(secret_source),
        )
        function = execution.update_zone

    assert client.request.call_args.kwargs["data"]["access_key"] == "ACCESS"
    assert client.request.call_args.kwargs["data"]["secret_key"] == "SECRET"
    parameters = inspect.signature(function).parameters
    assert "access_key" not in parameters
    assert "secret_key" not in parameters
