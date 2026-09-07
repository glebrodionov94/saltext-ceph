"""Salt-facing composition for public RGW multisite topology and sync APIs."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph import rgw_multisite


def _call(operation, opts, pillar, context, profile, *args, **kwargs):
    client = ceph.get_client(opts, pillar, context, profile)
    return operation(client, *args, **kwargs).as_dict()


def get_sync_status(opts, pillar, context, daemon_name=None, profile="default"):
    """Return current-only multisite sync status."""
    return _call(rgw_multisite.get_sync_status, opts, pillar, context, profile, daemon_name)


def get_sync_policy(
    opts,
    pillar,
    context,
    bucket_name="",
    zonegroup_name="",
    all_policy=None,
    daemon_name="",
    profile="default",
):
    """Return a current-only sync policy."""
    return _call(
        rgw_multisite.get_sync_policy,
        opts,
        pillar,
        context,
        profile,
        bucket_name,
        zonegroup_name,
        all_policy,
        daemon_name,
    )


def get_sync_policy_group(
    opts, pillar, context, group_id, bucket_name="", daemon_name="", profile="default"
):
    """Return a current-only sync policy group."""
    return _call(
        rgw_multisite.get_sync_policy_group,
        opts,
        pillar,
        context,
        profile,
        group_id,
        bucket_name,
        daemon_name,
    )


def create_sync_policy_group(
    opts,
    pillar,
    context,
    group_id,
    status,
    bucket_name="",
    daemon_name="",
    profile="default",
):
    """Create a current-only sync policy group."""
    return _call(
        rgw_multisite.create_sync_policy_group,
        opts,
        pillar,
        context,
        profile,
        group_id,
        status,
        bucket_name,
        daemon_name,
    )


def update_sync_policy_group(
    opts,
    pillar,
    context,
    group_id,
    status,
    bucket_name="",
    daemon_name="",
    profile="default",
):
    """Update a current-only sync policy group."""
    return _call(
        rgw_multisite.update_sync_policy_group,
        opts,
        pillar,
        context,
        profile,
        group_id,
        status,
        bucket_name,
        daemon_name,
    )


def delete_sync_policy_group(
    opts,
    pillar,
    context,
    group_id,
    bucket_name="",
    daemon_name="",
    confirm=False,
    profile="default",
):
    """Delete a current-only sync policy group after confirmation."""
    return _call(
        rgw_multisite.delete_sync_policy_group,
        opts,
        pillar,
        context,
        profile,
        group_id,
        bucket_name,
        daemon_name,
        confirm,
    )


def create_sync_flow(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_multisite.create_sync_flow,
        opts,
        pillar,
        context,
        profile,
        flow_id,
        flow_type,
        group_id,
        source_zone,
        destination_zone,
        zones,
        bucket_name,
        daemon_name,
        confirm_remove,
    )


def delete_sync_flow(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_multisite.delete_sync_flow,
        opts,
        pillar,
        context,
        profile,
        flow_id,
        flow_type,
        group_id,
        source_zone,
        destination_zone,
        zones,
        bucket_name,
        daemon_name,
        confirm,
    )


def create_sync_pipe(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_multisite.create_sync_pipe,
        opts,
        pillar,
        context,
        profile,
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
    )


def delete_sync_pipe(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_multisite.delete_sync_pipe,
        opts,
        pillar,
        context,
        profile,
        group_id,
        pipe_id,
        source_zones,
        destination_zones,
        bucket_name,
        daemon_name,
        confirm,
    )


def create_realm(opts, pillar, context, realm_name, default=False, profile="default"):
    """Create an RGW realm."""
    return _call(rgw_multisite.create_realm, opts, pillar, context, profile, realm_name, default)


def list_realms(opts, pillar, context, replicable=None, profile="default"):
    """List RGW realms."""
    return _call(rgw_multisite.list_realms, opts, pillar, context, profile, replicable)


def get_realm(opts, pillar, context, realm_name, profile="default"):
    """Return an RGW realm."""
    return _call(rgw_multisite.get_realm, opts, pillar, context, profile, realm_name)


def get_all_realms_info(opts, pillar, context, profile="default"):
    """Return the complete realm topology."""
    return _call(rgw_multisite.get_all_realms_info, opts, pillar, context, profile)


def update_realm(
    opts,
    pillar,
    context,
    realm_name,
    new_realm_name,
    default=False,
    profile="default",
):
    """Update an RGW realm."""
    return _call(
        rgw_multisite.update_realm,
        opts,
        pillar,
        context,
        profile,
        realm_name,
        new_realm_name,
        default,
    )


def get_realm_tokens(opts, pillar, context, include_secrets=False, profile="default"):
    """Return realm tokens only after an explicit secret opt-in."""
    return _call(
        rgw_multisite.get_realm_tokens,
        opts,
        pillar,
        context,
        profile,
        include_secrets,
    )


def import_realm_token(
    opts,
    pillar,
    context,
    realm_token_source,
    zone_name,
    port,
    placement_spec=None,
    tier_type=None,
    include_secrets=False,
    profile="default",
):
    """Import an RGW realm token."""
    return _call(
        rgw_multisite.import_realm_token,
        opts,
        pillar,
        context,
        profile,
        common.secret_from_file(realm_token_source, "realm_token", required=True),
        zone_name,
        port,
        placement_spec,
        tier_type,
        include_secrets,
    )


def delete_realm(opts, pillar, context, realm_name, confirm=False, profile="default"):
    """Delete an RGW realm after confirmation."""
    return _call(
        rgw_multisite.delete_realm,
        opts,
        pillar,
        context,
        profile,
        realm_name,
        confirm,
    )


def create_zonegroup(
    opts,
    pillar,
    context,
    realm_name,
    zonegroup_name,
    default=None,
    master=None,
    zonegroup_endpoints=None,
    profile="default",
):
    """Create an RGW zonegroup."""
    return _call(
        rgw_multisite.create_zonegroup,
        opts,
        pillar,
        context,
        profile,
        realm_name,
        zonegroup_name,
        default,
        master,
        zonegroup_endpoints,
    )


def list_zonegroups(opts, pillar, context, profile="default"):
    """List RGW zonegroups."""
    return _call(rgw_multisite.list_zonegroups, opts, pillar, context, profile)


def get_zonegroup(opts, pillar, context, zonegroup_name, profile="default"):
    """Return an RGW zonegroup."""
    return _call(
        rgw_multisite.get_zonegroup,
        opts,
        pillar,
        context,
        profile,
        zonegroup_name,
    )


def get_all_zonegroups_info(opts, pillar, context, profile="default"):
    """Return the complete zonegroup topology."""
    return _call(rgw_multisite.get_all_zonegroups_info, opts, pillar, context, profile)


def update_zonegroup(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_multisite.update_zonegroup,
        opts,
        pillar,
        context,
        profile,
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
    )


def delete_zonegroup(
    opts,
    pillar,
    context,
    zonegroup_name,
    delete_pools=False,
    pools=None,
    realm_name=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW zonegroup after confirmation."""
    return _call(
        rgw_multisite.delete_zonegroup,
        opts,
        pillar,
        context,
        profile,
        zonegroup_name,
        delete_pools,
        pools,
        realm_name,
        confirm,
    )


def get_placement_target(opts, pillar, context, placement_id, profile="default"):
    """Return a current-only placement target."""
    return _call(
        rgw_multisite.get_placement_target,
        opts,
        pillar,
        context,
        profile,
        placement_id,
    )


def set_zonegroup_storage_classes(
    opts,
    pillar,
    context,
    zone_group,
    placement_targets,
    edit=False,
    profile="default",
):
    """Create or edit current-only zonegroup storage classes."""
    return _call(
        rgw_multisite.set_zonegroup_storage_classes,
        opts,
        pillar,
        context,
        profile,
        zone_group,
        placement_targets,
        edit=edit,
    )


def delete_zonegroup_storage_class(
    opts,
    pillar,
    context,
    placement_id,
    storage_class,
    zone_name="",
    confirm=False,
    profile="default",
):
    """Delete a current-only zonegroup storage class after confirmation."""
    return _call(
        rgw_multisite.delete_zonegroup_storage_class,
        opts,
        pillar,
        context,
        profile,
        placement_id,
        storage_class,
        zone_name,
        confirm,
    )


def create_zone(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_multisite.create_zone,
        opts,
        pillar,
        context,
        profile,
        zone_name,
        zonegroup_name,
        default,
        master,
        zone_endpoints,
        common.secret_from_file(access_key_source, "access_key"),
        common.secret_from_file(secret_key_source, "secret_key"),
        tier_type,
        sync_from,
        sync_from_all,
        include_secrets,
    )


def list_zones(opts, pillar, context, include_secrets=False, profile="default"):
    """List RGW zones."""
    return _call(
        rgw_multisite.list_zones,
        opts,
        pillar,
        context,
        profile,
        include_secrets,
    )


def get_zone(opts, pillar, context, zone_name, include_secrets=False, profile="default"):
    """Return an RGW zone."""
    return _call(
        rgw_multisite.get_zone,
        opts,
        pillar,
        context,
        profile,
        zone_name,
        include_secrets,
    )


def get_all_zones_info(opts, pillar, context, include_secrets=False, profile="default"):
    """Return complete RGW zone topology."""
    return _call(
        rgw_multisite.get_all_zones_info,
        opts,
        pillar,
        context,
        profile,
        include_secrets,
    )


def update_zone(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_multisite.update_zone,
        opts,
        pillar,
        context,
        profile,
        zone_name,
        new_zone_name,
        zonegroup_name,
        default,
        master,
        zone_endpoints,
        common.secret_from_file(access_key_source, "access_key"),
        common.secret_from_file(secret_key_source, "secret_key"),
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
    )


def delete_zone(
    opts,
    pillar,
    context,
    zone_name,
    delete_pools=False,
    pools=None,
    zonegroup_name=None,
    realm_name=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW zone after confirmation."""
    return _call(
        rgw_multisite.delete_zone,
        opts,
        pillar,
        context,
        profile,
        zone_name,
        delete_pools,
        pools,
        zonegroup_name,
        realm_name,
        confirm,
    )


def get_pool_names(opts, pillar, context, profile="default"):
    """Return pools available for RGW placement."""
    return _call(rgw_multisite.get_pool_names, opts, pillar, context, profile)


def create_system_user(
    opts,
    pillar,
    context,
    user_name,
    zone_name,
    include_secrets=False,
    profile="default",
):
    """Create an RGW zone system user."""
    return _call(
        rgw_multisite.create_system_user,
        opts,
        pillar,
        context,
        profile,
        user_name,
        zone_name,
        include_secrets,
    )


def get_user_list(
    opts,
    pillar,
    context,
    zone_name=None,
    realm_name=None,
    profile="default",
):
    """List users eligible for an RGW zone."""
    return _call(
        rgw_multisite.get_user_list,
        opts,
        pillar,
        context,
        profile,
        zone_name,
        realm_name,
    )


def set_zone_storage_class(
    opts,
    pillar,
    context,
    zone_name,
    placement_target,
    storage_class,
    data_pool,
    compression="",
    edit=False,
    profile="default",
):
    """Create or edit a current-only zone storage class."""
    return _call(
        rgw_multisite.set_zone_storage_class,
        opts,
        pillar,
        context,
        profile,
        zone_name,
        placement_target,
        storage_class,
        data_pool,
        compression,
        edit=edit,
    )
