"""Manage RBD images through the public Ceph Dashboard REST API."""

from saltext.ceph.utils.ceph import rbd_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rbd"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _call(operation, *args, profile="default", **kwargs):
    return salt_adapter.invoke(
        rbd_api.call,
        __opts__,
        __pillar__,
        __context__,
        operation,
        *args,
        profile=profile,
        **kwargs,
    )


def list_(pool_name=None, namespace=None, offset=0, limit=5, search="", sort="", profile="default"):
    """List images. CLI Example: ``salt-call --local ceph_rbd.list pool_name=rbd``"""
    return _call("list", pool_name, namespace, offset, limit, search, sort, profile=profile)


def get(image_spec, omit_usage=False, profile="default"):
    """Return an image. CLI Example: ``salt-call --local ceph_rbd.get rbd/vm-1``"""
    return _call("get", image_spec, omit_usage, profile=profile)


def create(
    name,
    pool_name,
    size,
    namespace=None,
    schedule_interval=None,
    obj_size=None,
    features=None,
    stripe_unit=None,
    stripe_count=None,
    data_pool=None,
    configuration=None,
    metadata=None,
    mirror_mode=None,
    profile="default",
):
    """Create an image. CLI Example: ``salt-call --local ceph_rbd.create vm-1 rbd 1073741824``"""
    return _call(
        "create",
        name,
        pool_name,
        size,
        namespace,
        schedule_interval,
        obj_size,
        features,
        stripe_unit,
        stripe_count,
        data_pool,
        configuration,
        metadata,
        mirror_mode,
        profile=profile,
    )


def update(
    image_spec,
    name=None,
    size=None,
    features=None,
    configuration=None,
    metadata=None,
    enable_mirror=None,
    primary=None,
    force=False,
    resync=False,
    mirror_mode=None,
    image_mirror_mode=None,
    schedule_interval=None,
    remove_scheduling=False,
    schedule_level=None,
    confirm=False,
    profile="default",
):
    """Update an image. CLI Example: ``salt-call --local ceph_rbd.update rbd/vm-1 name=vm-2``"""
    return _call(
        "update",
        image_spec,
        name,
        size,
        features,
        configuration,
        metadata,
        enable_mirror,
        primary,
        force,
        resync,
        mirror_mode,
        image_mirror_mode,
        schedule_interval,
        remove_scheduling,
        schedule_level,
        confirm,
        profile=profile,
    )


def delete(image_spec, confirm=False, profile="default"):
    """Delete an image. CLI Example: ``salt-call --local ceph_rbd.delete rbd/vm-1 confirm=true``"""
    return _call("delete", image_spec, confirm, profile=profile)


def copy(
    image_spec,
    dest_pool_name,
    dest_namespace,
    dest_image_name,
    snapshot_name=None,
    obj_size=None,
    features=None,
    stripe_unit=None,
    stripe_count=None,
    data_pool=None,
    configuration=None,
    metadata=None,
    profile="default",
):
    """Copy an image. CLI Example: ``salt-call --local ceph_rbd.copy rbd/vm-1 backup '' vm-2``"""
    return _call(
        "copy",
        image_spec,
        dest_pool_name,
        dest_namespace,
        dest_image_name,
        snapshot_name,
        obj_size,
        features,
        stripe_unit,
        stripe_count,
        data_pool,
        configuration,
        metadata,
        profile=profile,
    )


def flatten(image_spec, confirm=False, profile="default"):
    """Flatten a clone. CLI Example: ``salt-call --local ceph_rbd.flatten rbd/vm-1 confirm=true``"""
    return _call("flatten", image_spec, confirm, profile=profile)


def default_features(profile="default"):
    """Return default features. CLI Example: ``salt-call --local ceph_rbd.default_features``"""
    return _call("default_features", profile=profile)


def clone_format_version(profile="default"):
    """Return clone format. CLI Example: ``salt-call --local ceph_rbd.clone_format_version``"""
    return _call("clone_format_version", profile=profile)


def move_to_trash(image_spec, delay=0, confirm=False, profile="default"):
    """Move to trash. CLI Example: ``salt-call --local ceph_rbd.move_to_trash rbd/vm-1 confirm=true``"""
    return _call("move_to_trash", image_spec, delay, confirm, profile=profile)


def trash_list(pool_name=None, profile="default"):
    """List trash. CLI Example: ``salt-call --local ceph_rbd.trash_list rbd``"""
    return _call("trash_list", pool_name, profile=profile)


def trash_purge(pool_name=None, confirm=False, profile="default"):
    """Purge trash. CLI Example: ``salt-call --local ceph_rbd.trash_purge rbd confirm=true``"""
    return _call("trash_purge", pool_name, confirm, profile=profile)


def trash_restore(image_id_spec, new_image_name, profile="default"):
    """Restore trash. CLI Example: ``salt-call --local ceph_rbd.trash_restore rbd/ID vm-1``"""
    return _call("trash_restore", image_id_spec, new_image_name, profile=profile)


def trash_delete(image_id_spec, force=False, confirm=False, profile="default"):
    """Delete trash. CLI Example: ``salt-call --local ceph_rbd.trash_delete rbd/ID confirm=true``"""
    return _call("trash_delete", image_id_spec, force, confirm, profile=profile)


def namespace_list(pool_name, profile="default"):
    """List namespaces. CLI Example: ``salt-call --local ceph_rbd.namespace_list rbd``"""
    return _call("namespace_list", pool_name, profile=profile)


def namespace_create(pool_name, namespace, profile="default"):
    """Create a namespace. CLI Example: ``salt-call --local ceph_rbd.namespace_create rbd tenant``"""
    return _call("namespace_create", pool_name, namespace, profile=profile)


def namespace_delete(pool_name, namespace, confirm=False, profile="default"):
    """Delete a namespace. CLI Example: ``salt-call --local ceph_rbd.namespace_delete rbd tenant confirm=true``"""
    return _call("namespace_delete", pool_name, namespace, confirm, profile=profile)


def snapshot_create(image_spec, snapshot_name, mirror_image_snapshot=False, profile="default"):
    """Create a snapshot. CLI Example: ``salt-call --local ceph_rbd.snapshot_create rbd/vm-1 s1``"""
    return _call(
        "snapshot_create",
        image_spec,
        snapshot_name,
        mirror_image_snapshot,
        profile=profile,
    )


def snapshot_update(
    image_spec,
    snapshot_name,
    new_snapshot_name=None,
    is_protected=None,
    profile="default",
):
    """Update a snapshot. CLI Example: ``salt-call --local ceph_rbd.snapshot_update rbd/vm-1 s1 is_protected=true``"""
    return _call(
        "snapshot_update",
        image_spec,
        snapshot_name,
        new_snapshot_name,
        is_protected,
        profile=profile,
    )


def snapshot_delete(image_spec, snapshot_name, confirm=False, profile="default"):
    """Delete a snapshot. CLI Example: ``salt-call --local ceph_rbd.snapshot_delete rbd/vm-1 s1 confirm=true``"""
    return _call("snapshot_delete", image_spec, snapshot_name, confirm, profile=profile)


def snapshot_rollback(image_spec, snapshot_name, confirm=False, profile="default"):
    """Rollback a snapshot. CLI Example: ``salt-call --local ceph_rbd.snapshot_rollback rbd/vm-1 s1 confirm=true``"""
    return _call("snapshot_rollback", image_spec, snapshot_name, confirm, profile=profile)


def snapshot_clone(
    image_spec,
    snapshot_name,
    child_pool_name,
    child_image_name,
    child_namespace=None,
    obj_size=None,
    features=None,
    stripe_unit=None,
    stripe_count=None,
    data_pool=None,
    configuration=None,
    metadata=None,
    clone_by_snap_id=False,
    profile="default",
):
    """Clone a snapshot. CLI Example: ``salt-call --local ceph_rbd.snapshot_clone rbd/vm-1 s1 backup vm-2``"""
    return _call(
        "snapshot_clone",
        image_spec,
        snapshot_name,
        child_pool_name,
        child_image_name,
        child_namespace,
        obj_size,
        features,
        stripe_unit,
        stripe_count,
        data_pool,
        configuration,
        metadata,
        clone_by_snap_id,
        profile=profile,
    )
