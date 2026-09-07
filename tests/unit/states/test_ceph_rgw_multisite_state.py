"""Declarative RGW multisite state tests."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_rgw_multisite as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def realm(**changes):
    value = {"id": "realm-id", "name": "realm-a", "epoch": 1}
    value.update(changes)
    return value


def realm_topology(realms=None, default=""):
    return {"realms": [realm()] if realms is None else realms, "default_realm": default}


def zonegroup(**changes):
    value = {
        "id": "zg-id",
        "name": "zg-a",
        "realm_id": "realm-id",
        "is_master": True,
        "master_zone": "zone-id",
        "endpoints": ["https://zg.example.test"],
        "zones": [
            {
                "id": "zone-id",
                "name": "zone-a",
                "endpoints": ["https://zone.example.test"],
            }
        ],
        "placement_targets": [
            {"name": "cold", "tags": ["archive"], "storage_classes": ["STANDARD"]}
        ],
    }
    value.update(changes)
    return value


def zonegroup_topology(zonegroups=None, default=""):
    return {
        "zonegroups": [zonegroup()] if zonegroups is None else zonegroups,
        "default_zonegroup": default,
    }


def zone(**changes):
    value = {
        "id": "zone-id",
        "name": "zone-a",
        "realm_id": "realm-id",
        "tier_type": "",
        "sync_from": ["zone-b"],
        "sync_from_all": False,
        "placement_pools": [
            {
                "key": "cold",
                "val": {
                    "storage_classes": {
                        "STANDARD": {
                            "data_pool": "rgw.data",
                            "compression_type": "zstd",
                        }
                    }
                },
            }
        ],
    }
    value.update(changes)
    return value


def zone_topology(zones=None, default=""):
    return {"zones": [zone()] if zones is None else zones, "default_zone": default}


def sync_group(**changes):
    value = {
        "id": "group-a",
        "status": "enabled",
        "data_flow": {
            "symmetrical": [{"id": "mirror", "zones": ["zone-a", "zone-b"]}],
            "directional": [{"id": "archive", "source_zone": "zone-a", "dest_zone": "zone-b"}],
        },
        "pipes": [
            {
                "id": "objects",
                "source": {"zones": ["zone-a"], "bucket": "source"},
                "dest": {"zones": ["zone-b"], "bucket": "destination"},
                "user": "sync-user",
                "mode": "system",
            }
        ],
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_realm_present_is_idempotent_with_default_id_projection(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_realms_info": Mock(
                return_value=envelope(realm_topology(default="realm-id"))
            ),
            "ceph_rgw_multisite.create_realm": create,
        },
    )
    result = state.realm_present("realm-a", default=True)
    assert result["result"] is True
    create.assert_not_called()


def test_realm_create_waits_and_post_reads(monkeypatch):
    topology = Mock(
        side_effect=[
            envelope(realm_topology(realms=[])),
            envelope(realm_topology(default="realm-id")),
        ]
    )
    create = Mock(
        return_value=envelope({"name": "rgw/realm/create", "metadata": {"realm": "realm-a"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_realms_info": topology,
            "ceph_rgw_multisite.create_realm": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.realm_present("realm-a", default=True)
    assert result["result"] is True
    wait.assert_called_once()


def test_realm_refuses_to_unset_current_default(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_realms_info": Mock(
                return_value=envelope(realm_topology(default="realm-id"))
            )
        },
    )
    result = state.realm_present("realm-a", default=False)
    assert result["result"] is False
    assert "another default" in result["comment"]


def test_realm_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_realms_info": Mock(return_value=envelope(realm_topology())),
            "ceph_rgw_multisite.delete_realm": delete,
        },
    )
    assert state.realm_absent("realm-a")["result"] is False
    delete.assert_not_called()


def test_zonegroup_present_is_idempotent(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_realms_info": Mock(return_value=envelope(realm_topology())),
            "ceph_rgw_multisite.get_all_zonegroups_info": Mock(
                return_value=envelope(zonegroup_topology(default="zg-id"))
            ),
            "ceph_rgw_multisite.update_zonegroup": update,
        },
    )
    result = state.zonegroup_present(
        "zg-a",
        "realm-a",
        default=True,
        master=True,
        endpoints=["https://zg.example.test"],
        zones=["zone-a"],
    )
    assert result["result"] is True
    update.assert_not_called()


def test_zonegroup_zone_removal_requires_confirmation(monkeypatch):
    group = zonegroup(
        zones=[
            {"id": "zone-id", "name": "zone-a", "endpoints": []},
            {"id": "zone-b-id", "name": "zone-b", "endpoints": []},
        ]
    )
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_realms_info": Mock(return_value=envelope(realm_topology())),
            "ceph_rgw_multisite.get_all_zonegroups_info": Mock(
                return_value=envelope(zonegroup_topology([group]))
            ),
            "ceph_rgw_multisite.update_zonegroup": Mock(),
        },
    )
    result = state.zonegroup_present("zg-a", "realm-a", zones=["zone-a"])
    assert result["result"] is False
    assert "confirm_remove" in result["comment"]


def test_zone_present_is_idempotent_and_does_not_need_secrets(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_zonegroups_info": Mock(
                return_value=envelope(zonegroup_topology())
            ),
            "ceph_rgw_multisite.get_all_zones_info": Mock(
                return_value=envelope(zone_topology(default="zone-id"))
            ),
            "ceph_rgw_multisite.update_zone": update,
        },
    )
    result = state.zone_present(
        "zone-a",
        "zg-a",
        default=True,
        master=True,
        endpoints=["https://zone.example.test"],
        sync_from=["zone-b"],
        sync_from_all=False,
    )
    assert result["result"] is True
    update.assert_not_called()


def test_zone_creation_keeps_secret_values_out_of_changes(monkeypatch, tmp_path):
    secret = tmp_path / "secret"
    secret.write_text("secret-value", encoding="utf-8")
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_zonegroups_info": Mock(
                return_value=envelope(zonegroup_topology())
            ),
            "ceph_rgw_multisite.get_all_zones_info": Mock(
                return_value=envelope(zone_topology(zones=[]))
            ),
        },
    )
    result = state.zone_present("zone-a", "zg-a", secret_key_source=str(secret))
    assert result["result"] is None
    assert "secret-value" not in str(result)
    assert "secret" not in result["changes"]["new"]


def test_placement_present_is_idempotent(monkeypatch):
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_zonegroups_info": Mock(
                return_value=envelope(zonegroup_topology())
            ),
            "ceph_rgw_multisite.set_zonegroup_storage_classes": set_,
        },
    )
    result = state.placement_present("cold", "zg-a", ["STANDARD"], tags=["archive"])
    assert result["result"] is True
    set_.assert_not_called()


def test_placement_storage_class_removal_requires_confirmation(monkeypatch):
    group = zonegroup(
        placement_targets=[
            {
                "name": "cold",
                "tags": [],
                "storage_classes": ["STANDARD", "GLACIER"],
            }
        ]
    )
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_zonegroups_info": Mock(
                return_value=envelope(zonegroup_topology([group]))
            )
        },
    )
    result = state.placement_present("cold", "zg-a", ["STANDARD"])
    assert result["result"] is False
    assert "confirm_remove" in result["comment"]


def test_storage_class_present_is_idempotent(monkeypatch):
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_zones_info": Mock(return_value=envelope(zone_topology())),
            "ceph_rgw_multisite.set_zone_storage_class": set_,
        },
    )
    result = state.storage_class_present(
        "STANDARD", "zone-a", "cold", "rgw.data", compression="zstd"
    )
    assert result["result"] is True
    set_.assert_not_called()


def test_storage_class_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_all_zones_info": Mock(return_value=envelope(zone_topology())),
            "ceph_rgw_multisite.delete_zonegroup_storage_class": delete,
        },
    )
    result = state.storage_class_absent("STANDARD", "zone-a", "cold")
    assert result["result"] is False
    delete.assert_not_called()


def test_sync_group_updates_and_post_reads(monkeypatch):
    before = sync_group(status="allowed")
    after = sync_group(status="enabled")
    get = Mock(side_effect=[envelope({"groups": [before]}), envelope({"groups": [after]})])
    update = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_sync_policy": get,
            "ceph_rgw_multisite.update_sync_policy_group": update,
        },
    )
    result = state.sync_group_present("group-a", "enabled")
    assert result["result"] is True
    update.assert_called_once()


def test_sync_group_disable_requires_confirmation(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_sync_policy": Mock(
                return_value=envelope({"groups": [sync_group()]})
            ),
            "ceph_rgw_multisite.update_sync_policy_group": update,
        },
    )
    result = state.sync_group_present("group-a", "forbidden")
    assert result["result"] is False
    assert "confirm_disable" in result["comment"]
    update.assert_not_called()


def test_sync_mutation_rejects_unscoped_zonegroup_selector(monkeypatch):
    monkeypatch.setattr(state, "__salt__", {})
    result = state.sync_group_present("group-a", "enabled", zonegroup_name="zg-a")
    assert result["result"] is False
    assert "daemon_name" in result["comment"]


def test_sync_group_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_sync_policy": Mock(
                return_value=envelope({"groups": [sync_group()]})
            ),
            "ceph_rgw_multisite.delete_sync_policy_group": delete,
        },
    )
    result = state.sync_group_absent("group-a")
    assert result["result"] is False
    delete.assert_not_called()


def test_symmetrical_flow_removal_requires_confirmation(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_sync_policy": Mock(
                return_value=envelope({"groups": [sync_group()]})
            )
        },
    )
    result = state.sync_flow_present("mirror", "symmetrical", "group-a", zones=["zone-a"])
    assert result["result"] is False
    assert "confirm_remove" in result["comment"]


def test_directional_flow_change_requires_confirmed_replace(monkeypatch):
    delete = Mock()
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_sync_policy": Mock(
                return_value=envelope({"groups": [sync_group()]})
            ),
            "ceph_rgw_multisite.delete_sync_flow": delete,
            "ceph_rgw_multisite.create_sync_flow": create,
        },
    )
    result = state.sync_flow_present(
        "archive",
        "directional",
        "group-a",
        source_zone="zone-a",
        destination_zone="zone-c",
    )
    assert result["result"] is False
    assert "confirm_replace" in result["comment"]
    delete.assert_not_called()


def test_symmetrical_flow_delta_is_applied_and_verified(monkeypatch):
    before = sync_group()
    after = deepcopy(before)
    after["data_flow"]["symmetrical"][0]["zones"] = ["zone-a", "zone-b", "zone-c"]
    get = Mock(side_effect=[envelope({"groups": [before]}), envelope({"groups": [after]})])
    create = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_multisite.get_sync_policy": get, "ceph_rgw_multisite.create_sync_flow": create},
    )
    result = state.sync_flow_present(
        "mirror", "symmetrical", "group-a", zones=["zone-a", "zone-b", "zone-c"]
    )
    assert result["result"] is True
    assert create.call_args.kwargs["zones"] == {"added": ["zone-c"], "removed": []}


def test_sync_pipe_is_idempotent(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_sync_policy": Mock(
                return_value=envelope({"groups": [sync_group()]})
            ),
            "ceph_rgw_multisite.create_sync_pipe": create,
        },
    )
    result = state.sync_pipe_present(
        "objects",
        "group-a",
        ["zone-a"],
        ["zone-b"],
        "source",
        "destination",
        user="sync-user",
        mode="system",
    )
    assert result["result"] is True
    create.assert_not_called()


def test_sync_pipe_bucket_change_requires_confirmed_replace(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_sync_policy": Mock(
                return_value=envelope({"groups": [sync_group()]})
            ),
            "ceph_rgw_multisite.delete_sync_pipe": delete,
        },
    )
    result = state.sync_pipe_present(
        "objects",
        "group-a",
        ["zone-a"],
        ["zone-b"],
        "new-source",
        "destination",
    )
    assert result["result"] is False
    assert "confirm_replace" in result["comment"]
    delete.assert_not_called()


def test_sync_pipe_zone_update_preserves_unmanaged_filter_fields(monkeypatch):
    before = sync_group()
    after = deepcopy(before)
    after["pipes"][0]["source"]["zones"] = ["zone-a", "zone-c"]
    get = Mock(side_effect=[envelope({"groups": [before]}), envelope({"groups": [after]})])
    create = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_multisite.get_sync_policy": get, "ceph_rgw_multisite.create_sync_pipe": create},
    )
    result = state.sync_pipe_present(
        "objects",
        "group-a",
        ["zone-a", "zone-c"],
        ["zone-b"],
        "source",
        "destination",
    )
    assert result["result"] is True
    assert create.call_args.kwargs["user"] == "sync-user"
    assert create.call_args.kwargs["mode"] == "system"


def test_sync_pipe_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_multisite.get_sync_policy": Mock(
                return_value=envelope({"groups": [sync_group()]})
            ),
            "ceph_rgw_multisite.delete_sync_pipe": delete,
        },
    )
    result = state.sync_pipe_absent("objects", "group-a")
    assert result["result"] is False
    delete.assert_not_called()
