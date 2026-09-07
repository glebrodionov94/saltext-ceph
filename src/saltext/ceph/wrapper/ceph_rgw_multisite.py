"""Manage RGW multisite operations from salt-ssh."""

from saltext.ceph.utils.ceph import rgw_multisite_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rgw_multisite"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def get_sync_status(daemon_name=None, profile="default"):
    """Return current-only multisite sync status."""
    return _invoke(rgw_multisite_api.get_sync_status, daemon_name, profile)


def get_sync_policy(
    bucket_name="", zonegroup_name="", all_policy=None, daemon_name="", profile="default"
):
    """Return a current-only sync policy."""
    return _invoke(
        rgw_multisite_api.get_sync_policy,
        bucket_name,
        zonegroup_name,
        all_policy,
        daemon_name,
        profile,
    )


def get_sync_policy_group(group_id, bucket_name="", daemon_name="", profile="default"):
    """Return a current-only sync policy group."""
    return _invoke(
        rgw_multisite_api.get_sync_policy_group, group_id, bucket_name, daemon_name, profile
    )


def create_sync_policy_group(group_id, status, bucket_name="", daemon_name="", profile="default"):
    """Create a current-only sync policy group."""
    return _invoke(
        rgw_multisite_api.create_sync_policy_group,
        group_id,
        status,
        bucket_name,
        daemon_name,
        profile,
    )


def update_sync_policy_group(group_id, status, bucket_name="", daemon_name="", profile="default"):
    """Update a current-only sync policy group."""
    return _invoke(
        rgw_multisite_api.update_sync_policy_group,
        group_id,
        status,
        bucket_name,
        daemon_name,
        profile,
    )


def delete_sync_policy_group(
    group_id, bucket_name="", daemon_name="", confirm=False, profile="default"
):
    """Delete a current-only sync policy group after confirmation."""
    return _invoke(
        rgw_multisite_api.delete_sync_policy_group,
        group_id,
        bucket_name,
        daemon_name,
        confirm,
        profile,
    )


def create_sync_flow(
    flow_id,
    flow_type,
    group_id,
    source_zone=None,
    destination_zone=None,
    zones=None,
    bucket_name="",
    daemon_name="",
    confirm_remove=False,
    profile="default",
):
    """Create or replace a current-only sync flow."""
    return _invoke(
        rgw_multisite_api.create_sync_flow,
        flow_id,
        flow_type,
        group_id,
        source_zone,
        destination_zone,
        zones,
        bucket_name,
        daemon_name,
        confirm_remove,
        profile,
    )


def delete_sync_flow(
    flow_id,
    flow_type,
    group_id,
    source_zone="",
    destination_zone="",
    zones=None,
    bucket_name="",
    daemon_name="",
    confirm=False,
    profile="default",
):
    """Delete a current-only sync flow after confirmation."""
    return _invoke(
        rgw_multisite_api.delete_sync_flow,
        flow_id,
        flow_type,
        group_id,
        source_zone,
        destination_zone,
        zones,
        bucket_name,
        daemon_name,
        confirm,
        profile,
    )


def create_sync_pipe(
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
    profile="default",
):
    """Create or replace a current-only sync pipe."""
    return _invoke(
        rgw_multisite_api.create_sync_pipe,
        group_id,
        pipe_id,
        source_zones,
        destination_zones,
        source_bucket,
        destination_bucket,
        bucket_name,
        user,
        mode,
        daemon_name,
        confirm_remove,
        profile,
    )


def delete_sync_pipe(
    group_id,
    pipe_id,
    source_zones=None,
    destination_zones=None,
    bucket_name="",
    daemon_name="",
    confirm=False,
    profile="default",
):
    """Delete a current-only sync pipe after confirmation."""
    return _invoke(
        rgw_multisite_api.delete_sync_pipe,
        group_id,
        pipe_id,
        source_zones,
        destination_zones,
        bucket_name,
        daemon_name,
        confirm,
        profile,
    )


def create_realm(realm_name, default=False, profile="default"):
    """Create an RGW realm."""
    return _invoke(rgw_multisite_api.create_realm, realm_name, default, profile)


def list_realms(replicable=None, profile="default"):
    """List RGW realms."""
    return _invoke(rgw_multisite_api.list_realms, replicable, profile)


def get_realm(realm_name, profile="default"):
    """Return an RGW realm."""
    return _invoke(rgw_multisite_api.get_realm, realm_name, profile)


def get_all_realms_info(profile="default"):
    """Return the complete realm topology."""
    return _invoke(rgw_multisite_api.get_all_realms_info, profile)


def update_realm(realm_name, new_realm_name, default=False, profile="default"):
    """Update an RGW realm."""
    return _invoke(rgw_multisite_api.update_realm, realm_name, new_realm_name, default, profile)


def get_realm_tokens(include_secrets=False, profile="default"):
    """Return realm tokens only after an explicit secret opt-in."""
    return _invoke(rgw_multisite_api.get_realm_tokens, include_secrets, profile)


def import_realm_token(
    realm_token_source,
    zone_name,
    port,
    placement_spec=None,
    tier_type=None,
    include_secrets=False,
    profile="default",
):
    """Import an RGW realm token."""
    return _invoke(
        rgw_multisite_api.import_realm_token,
        realm_token_source,
        zone_name,
        port,
        placement_spec,
        tier_type,
        include_secrets,
        profile,
    )


def delete_realm(realm_name, confirm=False, profile="default"):
    """Delete an RGW realm after confirmation."""
    return _invoke(rgw_multisite_api.delete_realm, realm_name, confirm, profile)


def create_zonegroup(
    realm_name,
    zonegroup_name,
    default=None,
    master=None,
    zonegroup_endpoints=None,
    profile="default",
):
    """Create an RGW zonegroup."""
    return _invoke(
        rgw_multisite_api.create_zonegroup,
        realm_name,
        zonegroup_name,
        default,
        master,
        zonegroup_endpoints,
        profile,
    )


def list_zonegroups(profile="default"):
    """List RGW zonegroups."""
    return _invoke(rgw_multisite_api.list_zonegroups, profile)


def get_zonegroup(zonegroup_name, profile="default"):
    """Return an RGW zonegroup."""
    return _invoke(rgw_multisite_api.get_zonegroup, zonegroup_name, profile)


def get_all_zonegroups_info(profile="default"):
    """Return the complete zonegroup topology."""
    return _invoke(rgw_multisite_api.get_all_zonegroups_info, profile)


def update_zonegroup(
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
    profile="default",
):
    """Update an RGW zonegroup."""
    return _invoke(
        rgw_multisite_api.update_zonegroup,
        zonegroup_name,
        realm_name,
        new_zonegroup_name,
        default,
        master,
        zonegroup_endpoints,
        add_zones,
        remove_zones,
        placement_targets,
        confirm_remove,
        profile,
    )


def delete_zonegroup(
    zonegroup_name,
    delete_pools=False,
    pools=None,
    realm_name=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW zonegroup after confirmation."""
    return _invoke(
        rgw_multisite_api.delete_zonegroup,
        zonegroup_name,
        delete_pools,
        pools,
        realm_name,
        confirm,
        profile,
    )


def get_placement_target(placement_id, profile="default"):
    """Return a current-only placement target."""
    return _invoke(rgw_multisite_api.get_placement_target, placement_id, profile)


def set_zonegroup_storage_classes(zone_group, placement_targets, edit=False, profile="default"):
    """Create or edit current-only zonegroup storage classes."""
    return _invoke(
        rgw_multisite_api.set_zonegroup_storage_classes,
        zone_group,
        placement_targets,
        edit,
        profile,
    )


def delete_zonegroup_storage_class(
    placement_id, storage_class, zone_name="", confirm=False, profile="default"
):
    """Delete a current-only zonegroup storage class after confirmation."""
    return _invoke(
        rgw_multisite_api.delete_zonegroup_storage_class,
        placement_id,
        storage_class,
        zone_name,
        confirm,
        profile,
    )


def create_zone(
    zone_name,
    zonegroup_name=None,
    default=False,
    master=False,
    zone_endpoints=None,
    access_key_source=None,
    secret_key_source=None,
    tier_type=None,
    sync_from=None,
    sync_from_all=None,
    include_secrets=False,
    profile="default",
):
    """Create an RGW zone."""
    return _invoke(
        rgw_multisite_api.create_zone,
        zone_name,
        zonegroup_name,
        default,
        master,
        zone_endpoints,
        access_key_source,
        secret_key_source,
        tier_type,
        sync_from,
        sync_from_all,
        include_secrets,
        profile,
    )


def list_zones(include_secrets=False, profile="default"):
    """List RGW zones."""
    return _invoke(rgw_multisite_api.list_zones, include_secrets, profile)


def get_zone(zone_name, include_secrets=False, profile="default"):
    """Return an RGW zone."""
    return _invoke(rgw_multisite_api.get_zone, zone_name, include_secrets, profile)


def get_all_zones_info(include_secrets=False, profile="default"):
    """Return complete RGW zone topology."""
    return _invoke(rgw_multisite_api.get_all_zones_info, include_secrets, profile)


def update_zone(
    zone_name,
    new_zone_name,
    zonegroup_name,
    default=False,
    master=False,
    zone_endpoints="",
    access_key_source=None,
    secret_key_source=None,
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
    profile="default",
):
    """Update an RGW zone."""
    return _invoke(
        rgw_multisite_api.update_zone,
        zone_name,
        new_zone_name,
        zonegroup_name,
        default,
        master,
        zone_endpoints,
        access_key_source,
        secret_key_source,
        placement_target,
        data_pool,
        index_pool,
        data_extra_pool,
        storage_class,
        data_pool_class,
        compression,
        tier_type,
        sync_from,
        sync_from_all,
        include_secrets,
        profile,
    )


def delete_zone(
    zone_name,
    delete_pools=False,
    pools=None,
    zonegroup_name=None,
    realm_name=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW zone after confirmation."""
    return _invoke(
        rgw_multisite_api.delete_zone,
        zone_name,
        delete_pools,
        pools,
        zonegroup_name,
        realm_name,
        confirm,
        profile,
    )


def get_pool_names(profile="default"):
    """Return pools available for RGW placement."""
    return _invoke(rgw_multisite_api.get_pool_names, profile)


def create_system_user(user_name, zone_name, include_secrets=False, profile="default"):
    """Create an RGW zone system user."""
    return _invoke(
        rgw_multisite_api.create_system_user, user_name, zone_name, include_secrets, profile
    )


def get_user_list(zone_name=None, realm_name=None, profile="default"):
    """List users eligible for an RGW zone."""
    return _invoke(rgw_multisite_api.get_user_list, zone_name, realm_name, profile)


def set_zone_storage_class(
    zone_name,
    placement_target,
    storage_class,
    data_pool,
    compression="",
    edit=False,
    profile="default",
):
    """Create or edit a current-only zone storage class."""
    return _invoke(
        rgw_multisite_api.set_zone_storage_class,
        zone_name,
        placement_target,
        storage_class,
        data_pool,
        compression,
        edit,
        profile,
    )
