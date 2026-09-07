"""Declaratively reconcile readable Ceph RGW multisite resources."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph import rgw_state
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_rgw_multisite"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_SYNC_STATUSES = frozenset(("enabled", "allowed", "forbidden"))


def __virtual__():
    required = {
        "ceph_rgw_multisite.get_all_realms_info",
        "ceph_rgw_multisite.get_all_zonegroups_info",
        "ceph_rgw_multisite.get_all_zones_info",
        "ceph_rgw_multisite.create_realm",
        "ceph_rgw_multisite.update_realm",
        "ceph_rgw_multisite.delete_realm",
        "ceph_rgw_multisite.create_zonegroup",
        "ceph_rgw_multisite.update_zonegroup",
        "ceph_rgw_multisite.delete_zonegroup",
        "ceph_rgw_multisite.create_zone",
        "ceph_rgw_multisite.update_zone",
        "ceph_rgw_multisite.delete_zone",
        "ceph_rgw_multisite.set_zonegroup_storage_classes",
        "ceph_rgw_multisite.delete_zonegroup_storage_class",
        "ceph_rgw_multisite.set_zone_storage_class",
        "ceph_rgw_multisite.get_sync_policy",
        "ceph_rgw_multisite.create_sync_policy_group",
        "ceph_rgw_multisite.update_sync_policy_group",
        "ceph_rgw_multisite.delete_sync_policy_group",
        "ceph_rgw_multisite.create_sync_flow",
        "ceph_rgw_multisite.delete_sync_flow",
        "ceph_rgw_multisite.create_sync_pipe",
        "ceph_rgw_multisite.delete_sync_pipe",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _wait(response, profile, timeout, interval):
    return reconcile.wait_if_accepted(
        __salt__, response, profile=profile, timeout=timeout, interval=interval
    )


def _topology(function, collection, label, profile, **kwargs):
    value = reconcile.data(__salt__[function](profile=profile, **kwargs), label, expected=Mapping)
    values = value.get(collection, [])
    return dict(value), rgw_state.list_of_mappings(values, label)


def _by_name(values, name, label):
    matches = [item for item in values if item.get("name") == name]
    if len(matches) > 1:
        raise ProtocolError(f"{label} returned duplicate resource {name}.")
    return matches[0] if matches else None


def _realm(name, profile):
    topology, values = _topology(
        "ceph_rgw_multisite.get_all_realms_info",
        "realms",
        "RGW realm topology",
        profile,
    )
    return topology, _by_name(values, name, "RGW realm topology")


def _realm_view(topology, current, desired):
    if current is None:
        return None
    result = {"name": current.get("name")}
    if "default" in desired:
        identifier = current.get("id")
        if not isinstance(identifier, str):
            raise ProtocolError("RGW realm read omitted its id.")
        result["default"] = topology.get("default_realm") == identifier
    return result


def realm_present(
    name,
    default=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an RGW realm exists and optionally is the default realm."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "realm_name")
        default = rgw_state.bool_or_none(default, "default")
        desired = {"name": name}
        if default is not None:
            desired["default"] = default
        topology, current = _realm(name, profile)
        old = _realm_view(topology, current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW realm {name} is current.")
        if current is not None and old.get("default") is True and default is False:
            raise ConfigurationError(
                "Ceph cannot unset the default realm without selecting another default realm."
            )
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW realm {name} would be reconciled.")
        if current is None:
            response = __salt__["ceph_rgw_multisite.create_realm"](
                name, default=default is True, profile=profile
            )
        else:
            response = __salt__["ceph_rgw_multisite.update_realm"](
                name, name, default=default is True, profile=profile
            )
        _wait(response, profile, task_timeout, task_interval)
        after_topology, after_resource = _realm(name, profile)
        after = _realm_view(after_topology, after_resource, desired)
        if after != desired:
            raise ProtocolError(f"RGW realm {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW realm {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def realm_absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an RGW realm is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "realm_name")
        confirm = common.boolean(confirm, "confirm")
        _, current = _realm(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW realm {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW realm {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW realm requires confirm=True.")
        response = __salt__["ceph_rgw_multisite.delete_realm"](name, confirm=True, profile=profile)
        _wait(response, profile, task_timeout, task_interval)
        if _realm(name, profile)[1] is not None:
            raise ProtocolError(f"RGW realm {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW realm {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _zonegroup(name, profile):
    topology, values = _topology(
        "ceph_rgw_multisite.get_all_zonegroups_info",
        "zonegroups",
        "RGW zonegroup topology",
        profile,
    )
    return topology, _by_name(values, name, "RGW zonegroup topology")


def _zone_names(current):
    values = current.get("zones", [])
    values = rgw_state.list_of_mappings(values, "RGW zonegroup zones")
    result = []
    for item in values:
        name = item.get("name")
        if not isinstance(name, str):
            raise ProtocolError("RGW zonegroup zone entry omitted its name.")
        result.append(name)
    if len(result) != len(set(result)):
        raise ProtocolError("RGW zonegroup contains duplicate zones.")
    return sorted(result)


def _endpoints(value, label):
    if value is None:
        return None
    if isinstance(value, str):
        values = [item.strip() for item in value.split(",") if item.strip()]
        return rgw_state.names(values, label)
    return rgw_state.names(value, label)


def _zonegroup_view(topology, current, desired):
    if current is None:
        return None
    result = {"name": current.get("name")}
    if "realm_id" in desired:
        result["realm_id"] = current.get("realm_id")
    if "default" in desired:
        result["default"] = topology.get("default_zonegroup") == current.get("id")
    if "master" in desired:
        result["master"] = rgw_state.response_bool(current.get("is_master"), "is_master")
    if "endpoints" in desired:
        result["endpoints"] = _endpoints(current.get("endpoints", []), "endpoints")
    if "zones" in desired:
        result["zones"] = _zone_names(current)
    return result


def zonegroup_present(
    name,
    realm_name,
    default=None,
    master=None,
    endpoints=None,
    zones=None,
    confirm_remove=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an RGW zonegroup's stable topology projection is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "zonegroup_name")
        realm_name = common.name(realm_name, "realm_name")
        default = rgw_state.bool_or_none(default, "default")
        master = rgw_state.bool_or_none(master, "master")
        endpoints = _endpoints(endpoints, "endpoints")
        zones = None if zones is None else rgw_state.names(zones, "zones")
        confirm_remove = common.boolean(confirm_remove, "confirm_remove")
        _, realm = _realm(realm_name, profile)
        if realm is None or not isinstance(realm.get("id"), str):
            raise ConfigurationError(f"RGW realm {realm_name} must exist before its zonegroup.")
        desired = {"name": name, "realm_id": realm["id"]}
        for key, value in {
            "default": default,
            "master": master,
            "endpoints": endpoints,
            "zones": zones,
        }.items():
            if value is not None:
                desired[key] = value
        topology, current = _zonegroup(name, profile)
        old = _zonegroup_view(topology, current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW zonegroup {name} is current.")
        if current is not None:
            if old.get("realm_id") != desired["realm_id"]:
                raise ConfigurationError(
                    "Moving an existing zonegroup between realms has no safe exact Dashboard "
                    "projection; create a replacement topology explicitly."
                )
            if old.get("default") is True and default is False:
                raise ConfigurationError(
                    "Ceph cannot unset the default zonegroup without selecting another default."
                )
            if old.get("master") is True and master is False:
                raise ConfigurationError(
                    "Ceph cannot demote a master zonegroup through this Dashboard endpoint."
                )
            if "endpoints" in desired and not endpoints and old.get("endpoints"):
                raise ConfigurationError(
                    "Ceph cannot clear zonegroup endpoints through this Dashboard endpoint."
                )
        current_zones = [] if current is None else _zone_names(current)
        additions = [] if zones is None else sorted(set(zones).difference(current_zones))
        removals = [] if zones is None else sorted(set(current_zones).difference(zones))
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW zonegroup {name} would be reconciled."
            )
        if removals and not confirm_remove:
            raise ConfigurationError("Removing zones requires confirm_remove=True.")
        if current is None:
            response = __salt__["ceph_rgw_multisite.create_zonegroup"](
                realm_name,
                name,
                default=default,
                master=master,
                zonegroup_endpoints=(None if endpoints is None else ",".join(endpoints)),
                profile=profile,
            )
        else:
            response = __salt__["ceph_rgw_multisite.update_zonegroup"](
                name,
                realm_name,
                name,
                default=(old.get("default", False) if default is None else default),
                master=(old.get("master", False) if master is None else master),
                zonegroup_endpoints=(
                    ",".join(old.get("endpoints", [])) if endpoints is None else ",".join(endpoints)
                ),
                add_zones=additions,
                remove_zones=removals,
                placement_targets=[],
                confirm_remove=bool(removals),
                profile=profile,
            )
        _wait(response, profile, task_timeout, task_interval)
        after_topology, after_resource = _zonegroup(name, profile)
        after = _zonegroup_view(after_topology, after_resource, desired)
        if after != desired:
            raise ProtocolError(f"RGW zonegroup {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW zonegroup {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def zonegroup_absent(
    name,
    realm_name=None,
    delete_pools=False,
    pools=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an RGW zonegroup is absent; optional pool removal is explicit."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "zonegroup_name")
        realm_name = common.optional_text(realm_name, "realm_name")
        delete_pools = common.boolean(delete_pools, "delete_pools")
        pools = rgw_state.names(pools or [], "pools")
        confirm = common.boolean(confirm, "confirm")
        _, current = _zonegroup(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW zonegroup {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW zonegroup {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW zonegroup requires confirm=True.")
        response = __salt__["ceph_rgw_multisite.delete_zonegroup"](
            name,
            delete_pools=delete_pools,
            pools=pools,
            realm_name=realm_name,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        if _zonegroup(name, profile)[1] is not None:
            raise ProtocolError(f"RGW zonegroup {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW zonegroup {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _zone(name, profile):
    topology, values = _topology(
        "ceph_rgw_multisite.get_all_zones_info",
        "zones",
        "RGW zone topology",
        profile,
        include_secrets=False,
    )
    return topology, _by_name(values, name, "RGW zone topology")


def _zone_member(zonegroup, name):
    values = rgw_state.list_of_mappings(zonegroup.get("zones", []), "RGW zonegroup zones")
    matches = [item for item in values if item.get("name") == name]
    if len(matches) > 1:
        raise ProtocolError(f"RGW zonegroup contains duplicate zone {name}.")
    return matches[0] if matches else None


def _zonegroup_membership(topology, name):
    """Return the unique zonegroup whose readable topology contains a zone."""
    values = rgw_state.list_of_mappings(topology.get("zonegroups", []), "RGW zonegroup topology")
    matches = [item for item in values if _zone_member(item, name) is not None]
    if len(matches) > 1:
        raise ProtocolError(f"RGW zone {name} belongs to multiple zonegroups.")
    return matches[0] if matches else None


def _zone_view(topology, current, zonegroup, desired):
    if current is None:
        return None
    member = _zone_member(zonegroup, desired["name"]) if zonegroup is not None else None
    result = {
        "name": current.get("name"),
        "zonegroup": zonegroup.get("name") if member is not None else None,
    }
    if "default" in desired:
        result["default"] = topology.get("default_zone") == current.get("id")
    if "master" in desired:
        result["master"] = zonegroup is not None and zonegroup.get("master_zone") == current.get(
            "id"
        )
    if "endpoints" in desired:
        result["endpoints"] = _endpoints(
            [] if member is None else member.get("endpoints", []), "endpoints"
        )
    if "tier_type" in desired:
        result["tier_type"] = current.get("tier_type")
    if "sync_from" in desired:
        result["sync_from"] = _endpoints(current.get("sync_from", []), "sync_from")
    if "sync_from_all" in desired:
        result["sync_from_all"] = rgw_state.response_bool(
            current.get("sync_from_all"), "sync_from_all"
        )
    return result


def zone_present(
    name,
    zonegroup_name,
    default=None,
    master=None,
    endpoints=None,
    tier_type=None,
    sync_from=None,
    sync_from_all=None,
    access_key_source=None,
    secret_key_source=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an RGW zone's stable topology projection is exact.

    System access and secret keys are creation-only because the zone read model
    masks them. Their file contents are never compared or exposed as changes.
    """
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "zone_name")
        zonegroup_name = common.name(zonegroup_name, "zonegroup_name")
        default = rgw_state.bool_or_none(default, "default")
        master = rgw_state.bool_or_none(master, "master")
        endpoints = _endpoints(endpoints, "endpoints")
        tier_type = common.optional_text(tier_type, "tier_type")
        sync_from = _endpoints(sync_from, "sync_from")
        sync_from_all = rgw_state.bool_or_none(sync_from_all, "sync_from_all")
        rgw_state.validate_secret_sources(access_key_source, secret_key_source)
        zonegroup_topology, target_zonegroup = _zonegroup(zonegroup_name, profile)
        if target_zonegroup is None:
            raise ConfigurationError(f"RGW zonegroup {zonegroup_name} must exist first.")
        desired = {"name": name, "zonegroup": zonegroup_name}
        for key, value in {
            "default": default,
            "master": master,
            "endpoints": endpoints,
            "tier_type": tier_type,
            "sync_from": sync_from,
            "sync_from_all": sync_from_all,
        }.items():
            if value is not None:
                desired[key] = value
        topology, current = _zone(name, profile)
        actual_zonegroup = _zonegroup_membership(zonegroup_topology, name)
        old = _zone_view(topology, current, actual_zonegroup, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW zone {name} is current.")
        if current is not None:
            if old.get("zonegroup") != zonegroup_name:
                raise ConfigurationError(
                    "Moving a zone between zonegroups is managed by zonegroup_present; declare "
                    "the membership there with confirm_remove=True where needed."
                )
            if old.get("default") is True and default is False:
                raise ConfigurationError(
                    "Ceph cannot unset the default zone without selecting another default."
                )
            if old.get("master") is True and master is False:
                raise ConfigurationError(
                    "Ceph cannot demote the master zone through this Dashboard endpoint."
                )
            if "endpoints" in desired and not endpoints and old.get("endpoints"):
                raise ConfigurationError(
                    "Ceph cannot clear zone endpoints through this Dashboard endpoint."
                )
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW zone {name} would be reconciled.")
        endpoint_text = None if endpoints is None else ",".join(endpoints)
        sync_text = None if sync_from is None else ",".join(sync_from)
        if current is None:
            response = __salt__["ceph_rgw_multisite.create_zone"](
                name,
                zonegroup_name=zonegroup_name,
                default=default is True,
                master=master is True,
                zone_endpoints=endpoint_text,
                access_key_source=access_key_source,
                secret_key_source=secret_key_source,
                tier_type=tier_type,
                sync_from=sync_text,
                sync_from_all=sync_from_all,
                include_secrets=False,
                profile=profile,
            )
        else:
            response = __salt__["ceph_rgw_multisite.update_zone"](
                name,
                name,
                zonegroup_name,
                default=(old.get("default", False) if default is None else default),
                master=(old.get("master", False) if master is None else master),
                zone_endpoints=(
                    ",".join(old.get("endpoints", [])) if endpoints is None else endpoint_text
                ),
                tier_type=tier_type,
                sync_from=sync_text,
                sync_from_all=sync_from_all,
                include_secrets=False,
                profile=profile,
            )
        _wait(response, profile, task_timeout, task_interval)
        after_topology, after_resource = _zone(name, profile)
        _, after_zonegroup = _zonegroup(zonegroup_name, profile)
        after = _zone_view(after_topology, after_resource, after_zonegroup, desired)
        if after != desired:
            raise ProtocolError(f"RGW zone {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW zone {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def zone_absent(
    name,
    zonegroup_name=None,
    realm_name=None,
    delete_pools=False,
    pools=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an RGW zone is absent; optional pool deletion is explicit."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "zone_name")
        zonegroup_name = common.optional_text(zonegroup_name, "zonegroup_name")
        realm_name = common.optional_text(realm_name, "realm_name")
        delete_pools = common.boolean(delete_pools, "delete_pools")
        pools = rgw_state.names(pools or [], "pools")
        confirm = common.boolean(confirm, "confirm")
        _, current = _zone(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW zone {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW zone {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW zone requires confirm=True.")
        response = __salt__["ceph_rgw_multisite.delete_zone"](
            name,
            delete_pools=delete_pools,
            pools=pools,
            zonegroup_name=zonegroup_name,
            realm_name=realm_name,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        if _zone(name, profile)[1] is not None:
            raise ProtocolError(f"RGW zone {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW zone {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _placement(zonegroup, placement_id):
    values = rgw_state.list_of_mappings(
        zonegroup.get("placement_targets", []), "RGW placement targets"
    )
    matches = [
        item
        for item in values
        if item.get("name", item.get("key", item.get("placement_id"))) == placement_id
    ]
    if len(matches) > 1:
        raise ProtocolError(f"RGW zonegroup contains duplicate placement {placement_id}.")
    return matches[0] if matches else None


def _placement_view(current, desired):
    if current is None:
        return None
    value = current.get("val", current)
    value = rgw_state.mapping(value, "RGW placement target")
    result = {"placement_id": desired["placement_id"]}
    classes = value.get("storage_classes", [])
    if isinstance(classes, Mapping):
        classes = list(classes)
    result["storage_classes"] = rgw_state.names(classes, "storage_classes")
    if "tags" in desired:
        tags = value.get("tags", [])
        if isinstance(tags, str):
            tags = [item for item in tags.split(",") if item]
        result["tags"] = rgw_state.names(tags, "tags")
    if "tier_type" in desired:
        result["tier_type"] = value.get("tier_type")
    if "tier_config" in desired:
        result["tier_config"] = rgw_state.canonical(value.get("tier_config", {}))
    return result


def placement_present(
    name,
    zonegroup_name,
    storage_classes,
    tags=None,
    tier_type=None,
    tier_config=None,
    confirm_remove=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure one current-Ceph zonegroup placement projection is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "placement_id")
        zonegroup_name = common.name(zonegroup_name, "zonegroup_name")
        storage_classes = rgw_state.names(storage_classes, "storage_classes")
        tags = None if tags is None else rgw_state.names(tags, "tags")
        tier_type = common.optional_text(tier_type, "tier_type")
        tier_config = (
            None
            if tier_config is None
            else rgw_state.json_value(tier_config, "tier_config", mapping_only=True)
        )
        confirm_remove = common.boolean(confirm_remove, "confirm_remove")
        _, zonegroup = _zonegroup(zonegroup_name, profile)
        if zonegroup is None:
            raise ConfigurationError(f"RGW zonegroup {zonegroup_name} must exist first.")
        desired = {"placement_id": name, "storage_classes": storage_classes}
        for key, value in {
            "tags": tags,
            "tier_type": tier_type,
            "tier_config": tier_config,
        }.items():
            if value is not None:
                desired[key] = rgw_state.canonical(value)
        current = _placement(zonegroup, name)
        old = _placement_view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW placement {name} is current.")
        old_classes = [] if old is None else old["storage_classes"]
        removals = sorted(set(old_classes).difference(storage_classes))
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW placement {name} would change.")
        if removals and not confirm_remove:
            raise ConfigurationError(
                "Removing placement storage classes requires confirm_remove=True."
            )
        for storage_class in removals:
            _wait(
                __salt__["ceph_rgw_multisite.delete_zonegroup_storage_class"](
                    name, storage_class, confirm=True, profile=profile
                ),
                profile,
                task_timeout,
                task_interval,
            )
        additions = sorted(set(storage_classes).difference(old_classes))
        update_classes = additions or ([] if current is not None else storage_classes)
        if (
            current is not None
            and not additions
            and any(
                old.get(key) != desired.get(key)
                for key in ("tags", "tier_type", "tier_config")
                if key in desired
            )
        ):
            update_classes = storage_classes or [""]
        if current is None and not storage_classes:
            update_classes = [""]
        for storage_class in update_classes:
            item = {
                "placement_id": name,
                "storage_class": storage_class,
                "tags": "" if tags is None else ",".join(tags),
            }
            if tier_type is not None:
                item["tier_type"] = tier_type
            if tier_config is not None:
                item["tier_config"] = tier_config
            _wait(
                __salt__["ceph_rgw_multisite.set_zonegroup_storage_classes"](
                    zonegroup_name, [item], edit=current is not None, profile=profile
                ),
                profile,
                task_timeout,
                task_interval,
            )
        _, after_zonegroup = _zonegroup(zonegroup_name, profile)
        if after_zonegroup is None:
            raise ProtocolError(
                f"RGW zonegroup {zonegroup_name} disappeared during reconciliation."
            )
        after = _placement_view(_placement(after_zonegroup, name), desired)
        if after != desired:
            raise ProtocolError(f"RGW placement {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW placement {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _zone_storage_class(zone, placement_id, storage_class):
    pools = rgw_state.list_of_mappings(zone.get("placement_pools", []), "RGW zone placements")
    placement = next(
        (item.get("val", item) for item in pools if item.get("key") == placement_id), None
    )
    if placement is None:
        return None
    placement = rgw_state.mapping(placement, "RGW zone placement")
    classes = placement.get("storage_classes", {})
    classes = rgw_state.mapping(classes, "RGW zone storage classes")
    value = classes.get(storage_class)
    if value is None:
        return None
    value = rgw_state.mapping(value, "RGW zone storage class")
    result = {"data_pool": value.get("data_pool")}
    compression = value.get("compression_type", value.get("compression"))
    if compression is not None:
        result["compression"] = compression
    return result


def storage_class_present(
    name,
    zone_name,
    placement_target,
    data_pool,
    compression=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure one current-Ceph zone storage-class mapping is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "storage_class")
        zone_name = common.name(zone_name, "zone_name")
        placement_target = common.name(placement_target, "placement_target")
        data_pool = common.name(data_pool, "data_pool")
        compression = common.optional_text(compression, "compression")
        desired = {"data_pool": data_pool}
        if compression is not None:
            desired["compression"] = compression
        _, zone = _zone(zone_name, profile)
        if zone is None:
            raise ConfigurationError(f"RGW zone {zone_name} must exist first.")
        current = _zone_storage_class(zone, placement_target, name)
        old = None if current is None else reconcile.project(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW storage class {zone_name}:{name} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW storage class {zone_name}:{name} would change."
            )
        response = __salt__["ceph_rgw_multisite.set_zone_storage_class"](
            zone_name,
            placement_target,
            name,
            data_pool,
            compression="" if compression is None else compression,
            edit=current is not None,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        _, after_zone = _zone(zone_name, profile)
        after_full = _zone_storage_class(after_zone, placement_target, name)
        after = None if after_full is None else reconcile.project(after_full, desired)
        if after != desired:
            raise ProtocolError(f"RGW storage class {zone_name}:{name} did not converge.")
        return reconcile.changed(
            ret, old, after, f"RGW storage class {zone_name}:{name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def storage_class_absent(
    name,
    zone_name,
    placement_target,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Remove a zone storage class and its same-named zonegroup placement class.

    This mirrors Ceph's public endpoint, which always removes from both scopes.
    """
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "storage_class")
        zone_name = common.name(zone_name, "zone_name")
        placement_target = common.name(placement_target, "placement_target")
        confirm = common.boolean(confirm, "confirm")
        _, zone = _zone(zone_name, profile)
        old = None if zone is None else _zone_storage_class(zone, placement_target, name)
        if old is None:
            return reconcile.no_change(
                ret, f"RGW storage class {zone_name}:{name} is already absent."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, None, f"RGW storage class {zone_name}:{name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting an RGW storage class requires confirm=True.")
        response = __salt__["ceph_rgw_multisite.delete_zonegroup_storage_class"](
            placement_target, name, zone_name=zone_name, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        _, after_zone = _zone(zone_name, profile)
        if after_zone is not None and _zone_storage_class(after_zone, placement_target, name):
            raise ProtocolError(f"RGW storage class {zone_name}:{name} still exists.")
        return reconcile.changed(
            ret, old, None, f"RGW storage class {zone_name}:{name} was deleted."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _sync_policy(bucket_name, zonegroup_name, daemon_name, profile):
    value = reconcile.data(
        __salt__["ceph_rgw_multisite.get_sync_policy"](
            bucket_name=bucket_name,
            zonegroup_name=zonegroup_name,
            daemon_name=daemon_name,
            profile=profile,
        ),
        "RGW sync policy",
        expected=Mapping,
    )
    groups = rgw_state.list_of_mappings(value.get("groups", []), "RGW sync policy groups")
    return dict(value), groups


def _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile):
    _, groups = _sync_policy(bucket_name, zonegroup_name, daemon_name, profile)
    matches = [group for group in groups if group.get("id", group.get("group_id")) == group_id]
    if len(matches) > 1:
        raise ProtocolError(f"RGW sync policy contains duplicate group {group_id}.")
    return matches[0] if matches else None


def _sync_context(bucket_name, zonegroup_name, daemon_name):
    bucket_name = common.optional_text(bucket_name, "bucket_name") or ""
    zonegroup_name = common.optional_text(zonegroup_name, "zonegroup_name") or ""
    daemon_name = common.optional_text(daemon_name, "daemon_name") or ""
    if zonegroup_name:
        raise ConfigurationError(
            "Dashboard sync-policy mutations cannot target zonegroup_name directly; select a "
            "daemon_name in that zonegroup instead."
        )
    return bucket_name, "", daemon_name


def sync_group_present(
    name,
    status,
    bucket_name="",
    zonegroup_name="",
    daemon_name="",
    confirm_disable=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph sync policy group has the declared status."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "group_id")
        status = common.name(status, "status").casefold()
        if status not in _SYNC_STATUSES:
            raise ConfigurationError("status must be enabled, allowed, or forbidden.")
        bucket_name, zonegroup_name, daemon_name = _sync_context(
            bucket_name, zonegroup_name, daemon_name
        )
        confirm_disable = common.boolean(confirm_disable, "confirm_disable")
        current = _sync_group(name, bucket_name, zonegroup_name, daemon_name, profile)
        old = None
        if current is not None:
            current_status = current.get("status")
            if not isinstance(current_status, str):
                raise ProtocolError("RGW sync policy group omitted its status.")
            old = {"group_id": name, "status": current_status.casefold()}
        desired = {"group_id": name, "status": status}
        if old == desired:
            return reconcile.no_change(ret, f"RGW sync group {name} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW sync group {name} would change.")
        if old is not None and old["status"] == "enabled" and status != "enabled":
            if not confirm_disable:
                raise ConfigurationError(
                    "Disabling an enabled sync group requires confirm_disable=True."
                )
        operation = (
            "ceph_rgw_multisite.create_sync_policy_group"
            if current is None
            else "ceph_rgw_multisite.update_sync_policy_group"
        )
        response = __salt__[operation](
            name,
            status,
            bucket_name=bucket_name,
            daemon_name=daemon_name,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after_group = _sync_group(name, bucket_name, zonegroup_name, daemon_name, profile)
        after = None
        if after_group is not None:
            after_status = after_group.get("status")
            if isinstance(after_status, str):
                after = {"group_id": name, "status": after_status.casefold()}
        if after != desired:
            raise ProtocolError(f"RGW sync group {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW sync group {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def sync_group_absent(
    name,
    bucket_name="",
    zonegroup_name="",
    daemon_name="",
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph sync policy group is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "group_id")
        bucket_name, zonegroup_name, daemon_name = _sync_context(
            bucket_name, zonegroup_name, daemon_name
        )
        confirm = common.boolean(confirm, "confirm")
        current = _sync_group(name, bucket_name, zonegroup_name, daemon_name, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW sync group {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW sync group {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW sync group requires confirm=True.")
        response = __salt__["ceph_rgw_multisite.delete_sync_policy_group"](
            name,
            bucket_name=bucket_name,
            daemon_name=daemon_name,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        if _sync_group(name, bucket_name, zonegroup_name, daemon_name, profile) is not None:
            raise ProtocolError(f"RGW sync group {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW sync group {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _flow_collection(group, flow_type):
    data_flow = rgw_state.mapping(group.get("data_flow", {}), "RGW sync data flow")
    aliases = (
        (flow_type, f"{flow_type}_flows")
        if flow_type == "symmetrical"
        else (flow_type, "directional_flows")
    )
    values = next((data_flow[key] for key in aliases if key in data_flow), [])
    return rgw_state.list_of_mappings(values, "RGW sync flows")


def _flow(group, flow_id, flow_type):
    values = _flow_collection(group, flow_type)
    matches = [item for item in values if item.get("id", item.get("flow_id")) == flow_id]
    if len(matches) > 1:
        raise ProtocolError(f"RGW sync group contains duplicate flow {flow_id}.")
    return matches[0] if matches else None


def _flow_view(current, desired):
    if current is None:
        return None
    result = {"flow_id": desired["flow_id"], "flow_type": desired["flow_type"]}
    if desired["flow_type"] == "symmetrical":
        result["zones"] = rgw_state.names(current.get("zones", []), "zones")
    else:
        source = current.get("source_zone", current.get("source"))
        destination = current.get(
            "destination_zone", current.get("dest_zone", current.get("destination"))
        )
        if not isinstance(source, str) or not isinstance(destination, str):
            raise ProtocolError("RGW directional sync flow omitted source or destination.")
        result.update({"source_zone": source, "destination_zone": destination})
    return result


def sync_flow_present(
    name,
    flow_type,
    group_id,
    source_zone=None,
    destination_zone=None,
    zones=None,
    bucket_name="",
    zonegroup_name="",
    daemon_name="",
    confirm_remove=False,
    confirm_replace=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph directional or symmetrical sync flow is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "flow_id")
        group_id = common.name(group_id, "group_id")
        flow_type = common.name(flow_type, "flow_type").casefold()
        if flow_type not in ("symmetrical", "directional"):
            raise ConfigurationError("flow_type must be symmetrical or directional.")
        bucket_name, zonegroup_name, daemon_name = _sync_context(
            bucket_name, zonegroup_name, daemon_name
        )
        confirm_remove = common.boolean(confirm_remove, "confirm_remove")
        confirm_replace = common.boolean(confirm_replace, "confirm_replace")
        desired = {"flow_id": name, "flow_type": flow_type}
        if flow_type == "symmetrical":
            if zones is None:
                raise ConfigurationError("symmetrical flows require zones.")
            desired["zones"] = rgw_state.names(zones, "zones")
        else:
            desired.update(
                {
                    "source_zone": common.name(source_zone, "source_zone"),
                    "destination_zone": common.name(destination_zone, "destination_zone"),
                }
            )
        group = _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile)
        if group is None:
            raise ConfigurationError(f"RGW sync group {group_id} must exist first.")
        current = _flow(group, name, flow_type)
        old = _flow_view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW sync flow {group_id}:{name} is current.")
        replacements = current is not None and flow_type == "directional"
        removals = []
        if current is not None and flow_type == "symmetrical":
            removals = sorted(set(old["zones"]).difference(desired["zones"]))
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW sync flow {group_id}:{name} would change."
            )
        if removals and not confirm_remove:
            raise ConfigurationError("Removing sync-flow zones requires confirm_remove=True.")
        if replacements:
            if not confirm_replace:
                raise ConfigurationError(
                    "Changing a directional sync flow requires confirm_replace=True."
                )
            _wait(
                __salt__["ceph_rgw_multisite.delete_sync_flow"](
                    name,
                    flow_type,
                    group_id,
                    source_zone=old["source_zone"],
                    destination_zone=old["destination_zone"],
                    bucket_name=bucket_name,
                    daemon_name=daemon_name,
                    confirm=True,
                    profile=profile,
                ),
                profile,
                task_timeout,
                task_interval,
            )
            current = None
        zone_delta = None
        if flow_type == "symmetrical":
            current_zones = [] if current is None else old["zones"]
            zone_delta = {
                "added": sorted(set(desired["zones"]).difference(current_zones)),
                "removed": sorted(set(current_zones).difference(desired["zones"])),
            }
        response = __salt__["ceph_rgw_multisite.create_sync_flow"](
            name,
            flow_type,
            group_id,
            source_zone=desired.get("source_zone"),
            destination_zone=desired.get("destination_zone"),
            zones=zone_delta,
            bucket_name=bucket_name,
            daemon_name=daemon_name,
            confirm_remove=bool(removals),
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after_group = _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile)
        after = (
            None
            if after_group is None
            else _flow_view(_flow(after_group, name, flow_type), desired)
        )
        if after != desired:
            raise ProtocolError(f"RGW sync flow {group_id}:{name} did not converge.")
        return reconcile.changed(
            ret, old, after, f"RGW sync flow {group_id}:{name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def sync_flow_absent(
    name,
    flow_type,
    group_id,
    bucket_name="",
    zonegroup_name="",
    daemon_name="",
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph sync flow is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "flow_id")
        group_id = common.name(group_id, "group_id")
        flow_type = common.name(flow_type, "flow_type").casefold()
        if flow_type not in ("symmetrical", "directional"):
            raise ConfigurationError("flow_type must be symmetrical or directional.")
        bucket_name, zonegroup_name, daemon_name = _sync_context(
            bucket_name, zonegroup_name, daemon_name
        )
        confirm = common.boolean(confirm, "confirm")
        group = _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile)
        current = None if group is None else _flow(group, name, flow_type)
        if current is None:
            return reconcile.no_change(ret, f"RGW sync flow {group_id}:{name} is already absent.")
        desired_shape = {"flow_id": name, "flow_type": flow_type}
        if flow_type == "symmetrical":
            desired_shape["zones"] = []
        else:
            desired_shape.update({"source_zone": "", "destination_zone": ""})
        old = _flow_view(current, desired_shape)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, None, f"RGW sync flow {group_id}:{name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting an RGW sync flow requires confirm=True.")
        response = __salt__["ceph_rgw_multisite.delete_sync_flow"](
            name,
            flow_type,
            group_id,
            source_zone=old.get("source_zone", ""),
            destination_zone=old.get("destination_zone", ""),
            zones=old.get("zones"),
            bucket_name=bucket_name,
            daemon_name=daemon_name,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        group = _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile)
        if group is not None and _flow(group, name, flow_type) is not None:
            raise ProtocolError(f"RGW sync flow {group_id}:{name} still exists.")
        return reconcile.changed(ret, old, None, f"RGW sync flow {group_id}:{name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _pipe(group, pipe_id):
    values = rgw_state.list_of_mappings(group.get("pipes", []), "RGW sync pipes")
    matches = [item for item in values if item.get("id", item.get("pipe_id")) == pipe_id]
    if len(matches) > 1:
        raise ProtocolError(f"RGW sync group contains duplicate pipe {pipe_id}.")
    return matches[0] if matches else None


def _pipe_side(current, *keys):
    value = next((current[key] for key in keys if key in current), {})
    return rgw_state.mapping(value, "RGW sync pipe endpoint")


def _pipe_user(current):
    value = current.get("user")
    if isinstance(value, str):
        return value
    params = current.get("params", {})
    if not isinstance(params, Mapping):
        return ""
    source = params.get("source", {})
    if not isinstance(source, Mapping):
        return ""
    filter_ = source.get("filter", {})
    if not isinstance(filter_, Mapping):
        return ""
    value = filter_.get("uid", "")
    return value if isinstance(value, str) else ""


def _pipe_view(current, desired):
    if current is None:
        return None
    source = _pipe_side(current, "source")
    destination = _pipe_side(current, "dest", "destination")
    source_zones = source.get("zones", current.get("source_zones", []))
    destination_zones = destination.get(
        "zones", current.get("destination_zones", current.get("dest_zones", []))
    )
    result = {
        "pipe_id": desired["pipe_id"],
        "source_zones": rgw_state.names(source_zones, "source_zones"),
        "destination_zones": rgw_state.names(destination_zones, "destination_zones"),
        "source_bucket": source.get(
            "bucket", source.get("bucket_name", current.get("source_bucket", ""))
        ),
        "destination_bucket": destination.get(
            "bucket",
            destination.get("bucket_name", current.get("destination_bucket", "")),
        ),
    }
    if "user" in desired:
        result["user"] = _pipe_user(current)
    if "mode" in desired:
        result["mode"] = current.get("mode", "")
    return result


def _pipe_desired(
    name, source_zones, destination_zones, source_bucket, destination_bucket, user, mode
):
    desired = {
        "pipe_id": common.name(name, "pipe_id"),
        "source_zones": rgw_state.names(source_zones, "source_zones"),
        "destination_zones": rgw_state.names(destination_zones, "destination_zones"),
        "source_bucket": common.name(source_bucket, "source_bucket"),
        "destination_bucket": common.name(destination_bucket, "destination_bucket"),
    }
    for key, value in {"user": user, "mode": mode}.items():
        value = common.optional_text(value, key)
        if value is not None:
            desired[key] = value
    return desired


def sync_pipe_present(
    name,
    group_id,
    source_zones,
    destination_zones,
    source_bucket,
    destination_bucket,
    bucket_name="",
    user=None,
    mode=None,
    zonegroup_name="",
    daemon_name="",
    confirm_remove=False,
    confirm_replace=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph sync pipe's readable projection is exact."""
    ret = reconcile.state_result(name)
    try:
        desired = _pipe_desired(
            name,
            source_zones,
            destination_zones,
            source_bucket,
            destination_bucket,
            user,
            mode,
        )
        name = desired["pipe_id"]
        group_id = common.name(group_id, "group_id")
        bucket_name, zonegroup_name, daemon_name = _sync_context(
            bucket_name, zonegroup_name, daemon_name
        )
        confirm_remove = common.boolean(confirm_remove, "confirm_remove")
        confirm_replace = common.boolean(confirm_replace, "confirm_replace")
        group = _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile)
        if group is None:
            raise ConfigurationError(f"RGW sync group {group_id} must exist first.")
        current = _pipe(group, name)
        old = _pipe_view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW sync pipe {group_id}:{name} is current.")
        source_removals = []
        destination_removals = []
        replace_required = False
        preserved_user = "" if current is None else _pipe_user(current)
        preserved_mode = "" if current is None else current.get("mode", "")
        if not isinstance(preserved_mode, str):
            raise ProtocolError("RGW sync pipe returned an invalid mode.")
        if current is not None:
            source_removals = sorted(set(old["source_zones"]).difference(desired["source_zones"]))
            destination_removals = sorted(
                set(old["destination_zones"]).difference(desired["destination_zones"])
            )
            replace_required = any(
                old.get(key) != desired.get(key)
                for key in ("source_bucket", "destination_bucket", "user", "mode")
                if key in desired
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW sync pipe {group_id}:{name} would change."
            )
        if (source_removals or destination_removals) and not confirm_remove:
            raise ConfigurationError("Removing sync-pipe zones requires confirm_remove=True.")
        if replace_required:
            if not confirm_replace:
                raise ConfigurationError(
                    "Changing sync-pipe buckets, user, or mode requires confirm_replace=True."
                )
            _wait(
                __salt__["ceph_rgw_multisite.delete_sync_pipe"](
                    group_id,
                    name,
                    source_zones=old["source_zones"],
                    destination_zones=old["destination_zones"],
                    bucket_name=bucket_name,
                    daemon_name=daemon_name,
                    confirm=True,
                    profile=profile,
                ),
                profile,
                task_timeout,
                task_interval,
            )
            current = None
        current_source = [] if current is None else old["source_zones"]
        current_destination = [] if current is None else old["destination_zones"]
        source_delta = {
            "added": sorted(set(desired["source_zones"]).difference(current_source)),
            "removed": sorted(set(current_source).difference(desired["source_zones"])),
        }
        destination_delta = {
            "added": sorted(set(desired["destination_zones"]).difference(current_destination)),
            "removed": sorted(set(current_destination).difference(desired["destination_zones"])),
        }
        response = __salt__["ceph_rgw_multisite.create_sync_pipe"](
            group_id,
            name,
            source_delta,
            destination_delta,
            source_bucket=desired["source_bucket"],
            destination_bucket=desired["destination_bucket"],
            bucket_name=bucket_name,
            user=desired.get("user", preserved_user),
            mode=desired.get("mode", preserved_mode),
            daemon_name=daemon_name,
            confirm_remove=bool(source_delta["removed"] or destination_delta["removed"]),
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after_group = _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile)
        after = None if after_group is None else _pipe_view(_pipe(after_group, name), desired)
        if after != desired:
            raise ProtocolError(f"RGW sync pipe {group_id}:{name} did not converge.")
        return reconcile.changed(
            ret, old, after, f"RGW sync pipe {group_id}:{name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def sync_pipe_absent(
    name,
    group_id,
    bucket_name="",
    zonegroup_name="",
    daemon_name="",
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph sync pipe is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "pipe_id")
        group_id = common.name(group_id, "group_id")
        bucket_name, zonegroup_name, daemon_name = _sync_context(
            bucket_name, zonegroup_name, daemon_name
        )
        confirm = common.boolean(confirm, "confirm")
        group = _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile)
        current = None if group is None else _pipe(group, name)
        if current is None:
            return reconcile.no_change(ret, f"RGW sync pipe {group_id}:{name} is already absent.")
        projection_keys = {
            "pipe_id": name,
            "source_zones": [],
            "destination_zones": [],
            "source_bucket": "",
            "destination_bucket": "",
        }
        old = _pipe_view(current, projection_keys)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, None, f"RGW sync pipe {group_id}:{name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting an RGW sync pipe requires confirm=True.")
        response = __salt__["ceph_rgw_multisite.delete_sync_pipe"](
            group_id,
            name,
            source_zones=old["source_zones"],
            destination_zones=old["destination_zones"],
            bucket_name=bucket_name,
            daemon_name=daemon_name,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        group = _sync_group(group_id, bucket_name, zonegroup_name, daemon_name, profile)
        if group is not None and _pipe(group, name) is not None:
            raise ProtocolError(f"RGW sync pipe {group_id}:{name} still exists.")
        return reconcile.changed(ret, old, None, f"RGW sync pipe {group_id}:{name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
