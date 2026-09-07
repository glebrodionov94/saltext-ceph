"""Public Ceph Dashboard RGW multisite, realm, zonegroup, and zone APIs."""

from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
SYNC_PATH = "/api/rgw/multisite"
REALM_PATH = "/api/rgw/realm"
ZONEGROUP_PATH = "/api/rgw/zonegroup"
ZONE_PATH = "/api/rgw/zone"
_SYNC_POLICY_STATUSES = frozenset(("enabled", "allowed", "forbidden"))


def _optional_bool(value, label):
    return None if value is None else common.boolean(value, label)


def _string_list_response(response, label):
    if not isinstance(response.data, list) or not all(
        isinstance(item, str) for item in response.data
    ):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    return common.safe_response(response, label, shape="list")


def _daemon(value):
    return common.optional_text(value, "daemon_name")


def _sync_params(bucket_name="", daemon_name=""):
    return {
        "bucket_name": common.optional_text(bucket_name, "bucket_name"),
        "daemon_name": common.optional_text(daemon_name, "daemon_name"),
    }


def get_sync_status(client, daemon_name=None):
    """Return the current-only RGW multisite sync status."""
    response = client.request(
        "GET",
        f"{SYNC_PATH}/sync_status",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name)),
    )
    return common.safe_response(response, "RGW multisite sync status")


def get_sync_policy(client, bucket_name="", zonegroup_name="", all_policy=None, daemon_name=""):
    """Return the current-only global or bucket sync policy."""
    response = client.request(
        "GET",
        f"{SYNC_PATH}/sync-policy",
        api_version=API_VERSION,
        params=common.params(
            bucket_name=common.optional_text(bucket_name, "bucket_name"),
            zonegroup_name=common.optional_text(zonegroup_name, "zonegroup_name"),
            all_policy=_optional_bool(all_policy, "all_policy"),
            daemon_name=common.optional_text(daemon_name, "daemon_name"),
        ),
    )
    return common.safe_response(response, "RGW multisite sync policy")


def get_sync_policy_group(client, group_id, bucket_name="", daemon_name=""):
    """Return one current-only sync policy group."""
    response = client.request(
        "GET",
        f"{SYNC_PATH}/sync-policy-group/{common.segment(group_id, 'group_id')}",
        api_version=API_VERSION,
        params=_sync_params(bucket_name, daemon_name),
    )
    return common.safe_response(response, "RGW multisite sync policy group")


def create_sync_policy_group(client, group_id, status, bucket_name="", daemon_name=""):
    """Create a current-only sync policy group."""
    status = common.name(status, "status").lower()
    if status not in _SYNC_POLICY_STATUSES:
        raise ConfigurationError("status must be enabled, allowed, or forbidden.")
    response = client.request(
        "POST",
        f"{SYNC_PATH}/sync-policy-group",
        api_version=API_VERSION,
        data={
            "group_id": common.name(group_id, "group_id"),
            "status": status,
            **_sync_params(bucket_name, daemon_name),
        },
    )
    return common.safe_response(response, "RGW sync policy group creation")


def update_sync_policy_group(client, group_id, status, bucket_name="", daemon_name=""):
    """Update a current-only sync policy group."""
    status = common.name(status, "status").lower()
    if status not in _SYNC_POLICY_STATUSES:
        raise ConfigurationError("status must be enabled, allowed, or forbidden.")
    response = client.request(
        "PUT",
        f"{SYNC_PATH}/sync-policy-group",
        api_version=API_VERSION,
        data={
            "group_id": common.name(group_id, "group_id"),
            "status": status,
            **_sync_params(bucket_name, daemon_name),
        },
    )
    return common.safe_response(response, "RGW sync policy group update")


def delete_sync_policy_group(client, group_id, bucket_name="", daemon_name="", confirm=False):
    """Delete a current-only sync policy group after confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{SYNC_PATH}/sync-policy-group/{common.segment(group_id, 'group_id')}",
        api_version=API_VERSION,
        params=_sync_params(bucket_name, daemon_name),
    )
    return common.safe_response(response, "RGW sync policy group deletion")


def _flow_type(value):
    value = common.name(value, "flow_type")
    if value not in ("symmetrical", "directional"):
        raise ConfigurationError("flow_type must be symmetrical or directional.")
    return value


def _zone_map(value, label):
    if value is None:
        return None
    value = common.mapping(value, label)
    if set(value) != {"added", "removed"}:
        raise ConfigurationError(f"{label} must contain added and removed lists.")
    return {key: common.string_list(items, f"{label} {key}") for key, items in value.items()}


def create_sync_flow(
    client,
    flow_id,
    flow_type,
    group_id,
    source_zone=None,
    destination_zone=None,
    zones=None,
    bucket_name="",
    daemon_name="",
    confirm_remove=False,
):
    """Create or replace a current-only directional or symmetrical sync flow."""
    flow_type = _flow_type(flow_type)
    if flow_type == "directional" and (source_zone is None or destination_zone is None):
        raise ConfigurationError("directional flows require source_zone and destination_zone.")
    if flow_type == "symmetrical" and zones is None:
        raise ConfigurationError("symmetrical flows require zones.")
    zones = _zone_map(zones, "zones")
    common.boolean(confirm_remove, "confirm_remove")
    if zones and zones["removed"]:
        common.confirm(confirm_remove)
    response = client.request(
        "PUT",
        f"{SYNC_PATH}/sync-flow",
        api_version=API_VERSION,
        data=common.params(
            flow_id=common.name(flow_id, "flow_id"),
            flow_type=flow_type,
            group_id=common.name(group_id, "group_id"),
            source_zone=common.optional_text(source_zone, "source_zone"),
            destination_zone=common.optional_text(destination_zone, "destination_zone"),
            zones=zones,
            **_sync_params(bucket_name, daemon_name),
        ),
    )
    return common.safe_response(response, "RGW sync flow update")


def delete_sync_flow(
    client,
    flow_id,
    flow_type,
    group_id,
    source_zone="",
    destination_zone="",
    zones=None,
    bucket_name="",
    daemon_name="",
    confirm=False,
):
    """Delete a current-only sync flow after confirmation."""
    common.confirm(confirm)
    flow_type = _flow_type(flow_type)
    if flow_type == "directional" and (not source_zone or not destination_zone):
        raise ConfigurationError("directional flows require source_zone and destination_zone.")
    response = client.request(
        "DELETE",
        f"{SYNC_PATH}/sync-flow/{common.segment(flow_id, 'flow_id')}/"
        f"{common.segment(flow_type, 'flow_type')}/"
        f"{common.segment(group_id, 'group_id')}",
        api_version=API_VERSION,
        params=common.params(
            source_zone=common.optional_text(source_zone, "source_zone"),
            destination_zone=common.optional_text(destination_zone, "destination_zone"),
            zones=common.string_list(zones, "zones", optional=True),
            **_sync_params(bucket_name, daemon_name),
        ),
    )
    return common.safe_response(response, "RGW sync flow deletion")


def create_sync_pipe(
    client,
    group_id,
    pipe_id,
    source_zones,
    destination_zones,
    source_bucket="",
    destination_bucket="",
    bucket_name="",
    user="",
    mode="",
    daemon_name="",
    confirm_remove=False,
):
    """Create or replace a current-only multisite sync pipe."""
    source_zones = _zone_map(source_zones, "source_zones")
    destination_zones = _zone_map(destination_zones, "destination_zones")
    common.boolean(confirm_remove, "confirm_remove")
    if source_zones["removed"] or destination_zones["removed"]:
        common.confirm(confirm_remove)
    response = client.request(
        "PUT",
        f"{SYNC_PATH}/sync-pipe",
        api_version=API_VERSION,
        data={
            "group_id": common.name(group_id, "group_id"),
            "pipe_id": common.name(pipe_id, "pipe_id"),
            "source_zones": source_zones,
            "destination_zones": destination_zones,
            "source_bucket": common.optional_text(source_bucket, "source_bucket"),
            "destination_bucket": common.optional_text(destination_bucket, "destination_bucket"),
            "bucket_name": common.optional_text(bucket_name, "bucket_name"),
            "user": common.optional_text(user, "user"),
            "mode": common.optional_text(mode, "mode"),
            "daemon_name": common.optional_text(daemon_name, "daemon_name"),
        },
    )
    return common.safe_response(response, "RGW sync pipe update")


def delete_sync_pipe(
    client,
    group_id,
    pipe_id,
    source_zones=None,
    destination_zones=None,
    bucket_name="",
    daemon_name="",
    confirm=False,
):
    """Delete a current-only sync pipe after confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{SYNC_PATH}/sync-pipe/{common.segment(group_id, 'group_id')}/"
        f"{common.segment(pipe_id, 'pipe_id')}",
        api_version=API_VERSION,
        params=common.params(
            source_zones=common.string_list(source_zones, "source_zones", optional=True),
            destination_zones=common.string_list(
                destination_zones, "destination_zones", optional=True
            ),
            **_sync_params(bucket_name, daemon_name),
        ),
    )
    return common.safe_response(response, "RGW sync pipe deletion")


def create_realm(client, realm_name, default=False):
    """Create an RGW realm."""
    response = client.request(
        "POST",
        REALM_PATH,
        api_version=API_VERSION,
        data={
            "realm_name": common.name(realm_name, "realm_name"),
            "default": common.boolean(default, "default"),
        },
    )
    return common.safe_response(response, "RGW realm creation")


def list_realms(client, replicable=None):
    """List realms; ``replicable`` is available only on current Ceph."""
    response = client.request(
        "GET",
        REALM_PATH,
        api_version=API_VERSION,
        params=common.params(replicable=_optional_bool(replicable, "replicable")),
    )
    shape = "list" if replicable is True else "mapping"
    return common.safe_response(response, "RGW realm list", shape=shape)


def get_realm(client, realm_name):
    """Return one RGW realm."""
    response = client.request(
        "GET",
        f"{REALM_PATH}/{common.segment(realm_name, 'realm_name')}",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW realm", shape="mapping")


def get_all_realms_info(client):
    """Return the complete realm topology."""
    response = client.request("GET", f"{REALM_PATH}/get_all_realms_info", api_version=API_VERSION)
    return common.safe_response(response, "RGW realm topology", shape="mapping")


def update_realm(client, realm_name, new_realm_name, default=False):
    """Rename a realm and optionally make it the default."""
    response = client.request(
        "PUT",
        f"{REALM_PATH}/{common.segment(realm_name, 'realm_name')}",
        api_version=API_VERSION,
        data={
            "new_realm_name": common.name(new_realm_name, "new_realm_name"),
            "default": common.boolean(default, "default"),
        },
    )
    return common.safe_response(response, "RGW realm update")


def get_realm_tokens(client, include_secrets=False):
    """Return realm bootstrap tokens only when ``include_secrets=True``."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request("GET", f"{REALM_PATH}/get_realm_tokens", api_version=API_VERSION)
    return common.secret_blob_response(
        response, "RGW realm tokens", include_secrets=include_secrets
    )


def import_realm_token(
    client,
    realm_token,
    zone_name,
    port,
    placement_spec=None,
    tier_type=None,
    include_secrets=False,
):
    """Import a realm token; optional placement/tier fields are current-only."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    if placement_spec is not None:
        placement_spec = common.json_value(placement_spec, "placement_spec")
        if not isinstance(placement_spec, (str, dict)):
            raise ConfigurationError("placement_spec must be text or a mapping.")
    response = client.request(
        "POST",
        f"{REALM_PATH}/import_realm_token",
        api_version=API_VERSION,
        data=common.params(
            realm_token=common.name(realm_token, "realm_token"),
            zone_name=common.name(zone_name, "zone_name"),
            port=common.positive(port, "port"),
            placement_spec=placement_spec,
            tier_type=common.optional_text(tier_type, "tier_type"),
        ),
    )
    return common.safe_response(response, "RGW realm import", include_secrets=include_secrets)


def delete_realm(client, realm_name, confirm=False):
    """Delete an RGW realm after explicit confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{REALM_PATH}/{common.segment(realm_name, 'realm_name')}",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW realm deletion")


def create_zonegroup(
    client,
    realm_name,
    zonegroup_name,
    default=None,
    master=None,
    zonegroup_endpoints=None,
):
    """Create an RGW zonegroup."""
    response = client.request(
        "POST",
        ZONEGROUP_PATH,
        api_version=API_VERSION,
        data=common.params(
            realm_name=common.name(realm_name, "realm_name"),
            zonegroup_name=common.name(zonegroup_name, "zonegroup_name"),
            default=_optional_bool(default, "default"),
            master=_optional_bool(master, "master"),
            zonegroup_endpoints=common.optional_text(zonegroup_endpoints, "zonegroup_endpoints"),
        ),
    )
    return common.safe_response(response, "RGW zonegroup creation")


def list_zonegroups(client):
    """List RGW zonegroup names."""
    response = client.request("GET", ZONEGROUP_PATH, api_version=API_VERSION)
    return common.safe_response(response, "RGW zonegroup list", shape="mapping")


def get_zonegroup(client, zonegroup_name):
    """Return one RGW zonegroup."""
    response = client.request(
        "GET",
        f"{ZONEGROUP_PATH}/{common.segment(zonegroup_name, 'zonegroup_name')}",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW zonegroup", shape="mapping")


def get_all_zonegroups_info(client):
    """Return the complete zonegroup topology."""
    response = client.request(
        "GET", f"{ZONEGROUP_PATH}/get_all_zonegroups_info", api_version=API_VERSION
    )
    return common.safe_response(response, "RGW zonegroup topology", shape="mapping")


def update_zonegroup(
    client,
    zonegroup_name,
    realm_name,
    new_zonegroup_name,
    default=False,
    master=False,
    zonegroup_endpoints="",
    add_zones=None,
    remove_zones=None,
    placement_targets=None,
    confirm_remove=False,
):
    """Update a zonegroup using structured zones and placement targets."""
    remove_zones = common.string_list(remove_zones or [], "remove_zones")
    common.boolean(confirm_remove, "confirm_remove")
    if remove_zones:
        common.confirm(confirm_remove)
    response = client.request(
        "PUT",
        f"{ZONEGROUP_PATH}/{common.segment(zonegroup_name, 'zonegroup_name')}",
        api_version=API_VERSION,
        data={
            "realm_name": common.name(realm_name, "realm_name"),
            "new_zonegroup_name": common.name(new_zonegroup_name, "new_zonegroup_name"),
            "default": common.boolean(default, "default"),
            "master": common.boolean(master, "master"),
            "zonegroup_endpoints": common.optional_text(zonegroup_endpoints, "zonegroup_endpoints"),
            "add_zones": common.string_list(add_zones or [], "add_zones"),
            "remove_zones": remove_zones,
            "placement_targets": common.mapping_list(placement_targets or [], "placement_targets"),
        },
    )
    return common.safe_response(response, "RGW zonegroup update")


def delete_zonegroup(
    client,
    zonegroup_name,
    delete_pools=False,
    pools=None,
    realm_name=None,
    confirm=False,
):
    """Delete a zonegroup and optionally listed pools after confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{ZONEGROUP_PATH}/{common.segment(zonegroup_name, 'zonegroup_name')}",
        api_version=API_VERSION,
        params=common.params(
            delete_pools=common.boolean(delete_pools, "delete_pools"),
            pools=common.string_list(pools or [], "pools"),
            realm_name=common.optional_text(realm_name, "realm_name"),
        ),
    )
    return common.safe_response(response, "RGW zonegroup deletion")


def get_placement_target(client, placement_id):
    """Return a current-only zonegroup placement target."""
    response = client.request(
        "GET",
        f"{ZONEGROUP_PATH}/get_placement_target_by_placement_id/"
        f"{common.segment(placement_id, 'placement_id')}",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW placement target")


def set_zonegroup_storage_classes(client, zone_group, placement_targets, *, edit=False):
    """Create or edit current-only zonegroup storage classes."""
    response = client.request(
        "PUT" if common.boolean(edit, "edit") else "POST",
        f"{ZONEGROUP_PATH}/storage-class",
        api_version=API_VERSION,
        data={
            "zone_group": common.name(zone_group, "zone_group"),
            "placement_targets": common.mapping_list(placement_targets, "placement_targets"),
        },
    )
    return common.safe_response(response, "RGW zonegroup storage class update")


def delete_zonegroup_storage_class(
    client, placement_id, storage_class, zone_name="", confirm=False
):
    """Delete a current-only zonegroup storage class after confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{ZONEGROUP_PATH}/storage-class/{common.segment(placement_id, 'placement_id')}/"
        f"{common.segment(storage_class, 'storage_class')}",
        api_version=API_VERSION,
        params={"zone_name": common.optional_text(zone_name, "zone_name")},
    )
    return common.safe_response(response, "RGW zonegroup storage class deletion")


def create_zone(
    client,
    zone_name,
    zonegroup_name=None,
    default=False,
    master=False,
    zone_endpoints=None,
    access_key=None,
    secret_key=None,
    tier_type=None,
    sync_from=None,
    sync_from_all=None,
    include_secrets=False,
):
    """Create a zone; tier and sync fields are current-only."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request(
        "POST",
        ZONE_PATH,
        api_version=API_VERSION,
        data=common.params(
            zone_name=common.name(zone_name, "zone_name"),
            zonegroup_name=common.optional_text(zonegroup_name, "zonegroup_name"),
            default=common.boolean(default, "default"),
            master=common.boolean(master, "master"),
            zone_endpoints=common.optional_text(zone_endpoints, "zone_endpoints"),
            access_key=common.optional_text(access_key, "access_key"),
            secret_key=common.optional_text(secret_key, "secret_key"),
            tier_type=common.optional_text(tier_type, "tier_type"),
            sync_from=common.optional_text(sync_from, "sync_from"),
            sync_from_all=_optional_bool(sync_from_all, "sync_from_all"),
        ),
    )
    return common.safe_response(response, "RGW zone creation", include_secrets=include_secrets)


def list_zones(client, include_secrets=False):
    """List RGW zones, redacting system credentials by default."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request("GET", ZONE_PATH, api_version=API_VERSION)
    return common.safe_response(
        response, "RGW zone list", shape="mapping", include_secrets=include_secrets
    )


def get_zone(client, zone_name, include_secrets=False):
    """Return one RGW zone, redacting system credentials by default."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request(
        "GET",
        f"{ZONE_PATH}/{common.segment(zone_name, 'zone_name')}",
        api_version=API_VERSION,
    )
    return common.safe_response(
        response, "RGW zone", shape="mapping", include_secrets=include_secrets
    )


def get_all_zones_info(client, include_secrets=False):
    """Return complete zone topology, redacting system credentials by default."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request("GET", f"{ZONE_PATH}/get_all_zones_info", api_version=API_VERSION)
    return common.safe_response(
        response,
        "RGW zone topology",
        shape="mapping",
        include_secrets=include_secrets,
    )


def update_zone(
    client,
    zone_name,
    new_zone_name,
    zonegroup_name,
    default=False,
    master=False,
    zone_endpoints="",
    access_key="",
    secret_key="",
    placement_target="",
    data_pool="",
    index_pool="",
    data_extra_pool="",
    storage_class="",
    data_pool_class="",
    compression="",
    tier_type=None,
    sync_from=None,
    sync_from_all=None,
    include_secrets=False,
):
    """Update a zone; tier and sync fields are current-only."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request(
        "PUT",
        f"{ZONE_PATH}/{common.segment(zone_name, 'zone_name')}",
        api_version=API_VERSION,
        data=common.params(
            new_zone_name=common.name(new_zone_name, "new_zone_name"),
            zonegroup_name=common.name(zonegroup_name, "zonegroup_name"),
            default=common.boolean(default, "default"),
            master=common.boolean(master, "master"),
            zone_endpoints=common.optional_text(zone_endpoints, "zone_endpoints"),
            access_key=common.optional_text(access_key, "access_key"),
            secret_key=common.optional_text(secret_key, "secret_key"),
            placement_target=common.optional_text(placement_target, "placement_target"),
            data_pool=common.optional_text(data_pool, "data_pool"),
            index_pool=common.optional_text(index_pool, "index_pool"),
            data_extra_pool=common.optional_text(data_extra_pool, "data_extra_pool"),
            storage_class=common.optional_text(storage_class, "storage_class"),
            data_pool_class=common.optional_text(data_pool_class, "data_pool_class"),
            compression=common.optional_text(compression, "compression"),
            tier_type=common.optional_text(tier_type, "tier_type"),
            sync_from=common.optional_text(sync_from, "sync_from"),
            sync_from_all=_optional_bool(sync_from_all, "sync_from_all"),
        ),
    )
    return common.safe_response(response, "RGW zone update", include_secrets=include_secrets)


def delete_zone(
    client,
    zone_name,
    delete_pools=False,
    pools=None,
    zonegroup_name=None,
    realm_name=None,
    confirm=False,
):
    """Delete a zone and optionally listed pools after confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{ZONE_PATH}/{common.segment(zone_name, 'zone_name')}",
        api_version=API_VERSION,
        params=common.params(
            delete_pools=common.boolean(delete_pools, "delete_pools"),
            pools=common.string_list(pools or [], "pools"),
            zonegroup_name=common.optional_text(zonegroup_name, "zonegroup_name"),
            realm_name=common.optional_text(realm_name, "realm_name"),
        ),
    )
    return common.safe_response(response, "RGW zone deletion")


def get_pool_names(client):
    """Return the pools available to RGW zone placement."""
    response = client.request("GET", f"{ZONE_PATH}/get_pool_names", api_version=API_VERSION)
    return common.safe_response(response, "RGW pool names", shape="mapping_list")


def create_system_user(client, user_name, zone_name, include_secrets=False):
    """Create a zone system user, returning its keys only with explicit opt-in."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request(
        "PUT",
        f"{ZONE_PATH}/create_system_user",
        api_version=API_VERSION,
        data={
            "userName": common.name(user_name, "user_name"),
            "zoneName": common.name(zone_name, "zone_name"),
        },
    )
    return common.safe_response(
        response, "RGW system user creation", include_secrets=include_secrets
    )


def get_user_list(client, zone_name=None, realm_name=None):
    """List users eligible for a zone; ``realm_name`` is current-only."""
    response = client.request(
        "GET",
        f"{ZONE_PATH}/get_user_list",
        api_version=API_VERSION,
        params=common.params(
            zoneName=common.optional_text(zone_name, "zone_name"),
            realmName=common.optional_text(realm_name, "realm_name"),
        ),
    )
    return _string_list_response(response, "RGW zone user list")


def set_zone_storage_class(
    client,
    zone_name,
    placement_target,
    storage_class,
    data_pool,
    compression="",
    *,
    edit=False,
):
    """Create or edit a current-only zone storage class."""
    response = client.request(
        "PUT" if common.boolean(edit, "edit") else "POST",
        f"{ZONE_PATH}/storage-class",
        api_version=API_VERSION,
        data={
            "zone_name": common.name(zone_name, "zone_name"),
            "placement_target": common.name(placement_target, "placement_target"),
            "storage_class": common.name(storage_class, "storage_class"),
            "data_pool": common.name(data_pool, "data_pool"),
            "compression": common.optional_text(compression, "compression"),
        },
    )
    return common.safe_response(response, "RGW zone storage class update")
