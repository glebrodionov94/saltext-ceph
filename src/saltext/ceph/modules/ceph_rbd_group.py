"""Manage current-Ceph RBD groups through the Dashboard REST API."""

from saltext.ceph.utils.ceph import rbd_group_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rbd_group"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _call(operation, *args, profile="default", **kwargs):
    return salt_adapter.invoke(
        rbd_group_api.call,
        __opts__,
        __pillar__,
        __context__,
        operation,
        *args,
        profile=profile,
        **kwargs,
    )


def list_(pool_name, namespace=None, profile="default"):
    """List groups. CLI Example: ``salt-call --local ceph_rbd_group.list rbd``"""
    return _call("list", pool_name, namespace, profile=profile)


def get(pool_name, group_name, namespace=None, profile="default"):
    """Return a group. CLI Example: ``salt-call --local ceph_rbd_group.get rbd group``"""
    return _call("get", pool_name, group_name, namespace, profile=profile)


def create(pool_name, name, namespace=None, profile="default"):
    """Create a group. CLI Example: ``salt-call --local ceph_rbd_group.create rbd group``"""
    return _call("create", pool_name, name, namespace, profile=profile)


def update(pool_name, group_name, new_name, namespace=None, profile="default"):
    """Rename a group. CLI Example: ``salt-call --local ceph_rbd_group.update rbd old new``"""
    return _call("update", pool_name, group_name, new_name, namespace, profile=profile)


def delete(pool_name, group_name, namespace=None, confirm=False, profile="default"):
    """Delete a group. CLI Example: ``salt-call --local ceph_rbd_group.delete rbd group confirm=true``"""
    return _call("delete", pool_name, group_name, namespace, confirm, profile=profile)


def add_image(pool_name, group_name, image_name, namespace=None, profile="default"):
    """Add an image. CLI Example: ``salt-call --local ceph_rbd_group.add_image rbd group vm-1``"""
    return _call("add_image", pool_name, group_name, image_name, namespace, profile=profile)


def remove_image(
    pool_name,
    group_name,
    image_name,
    namespace=None,
    confirm=False,
    profile="default",
):
    """Remove an image. CLI Example: ``salt-call --local ceph_rbd_group.remove_image rbd group vm-1 confirm=true``"""
    return _call(
        "remove_image",
        pool_name,
        group_name,
        image_name,
        namespace,
        confirm,
        profile=profile,
    )


def snapshot_list(pool_name, group_name, namespace=None, profile="default"):
    """List snapshots. CLI Example: ``salt-call --local ceph_rbd_group.snapshot_list rbd group``"""
    return _call("snapshot_list", pool_name, group_name, namespace, profile=profile)


def snapshot_get(pool_name, group_name, snapshot_name, namespace=None, profile="default"):
    """Return a snapshot. CLI Example: ``salt-call --local ceph_rbd_group.snapshot_get rbd group s1``"""
    return _call("snapshot_get", pool_name, group_name, snapshot_name, namespace, profile=profile)


def snapshot_create(
    pool_name,
    group_name,
    snapshot_name,
    namespace=None,
    flags=0,
    profile="default",
):
    """Create a snapshot. CLI Example: ``salt-call --local ceph_rbd_group.snapshot_create rbd group s1``"""
    return _call(
        "snapshot_create",
        pool_name,
        group_name,
        snapshot_name,
        namespace,
        flags,
        profile=profile,
    )


def snapshot_update(
    pool_name,
    group_name,
    snapshot_name,
    new_snapshot_name,
    namespace=None,
    profile="default",
):
    """Rename a snapshot. CLI Example: ``salt-call --local ceph_rbd_group.snapshot_update rbd group old new``"""
    return _call(
        "snapshot_update",
        pool_name,
        group_name,
        snapshot_name,
        new_snapshot_name,
        namespace,
        profile=profile,
    )


def snapshot_delete(
    pool_name,
    group_name,
    snapshot_name,
    namespace=None,
    confirm=False,
    profile="default",
):
    """Delete a snapshot. CLI Example: ``salt-call --local ceph_rbd_group.snapshot_delete rbd group s1 confirm=true``"""
    return _call(
        "snapshot_delete",
        pool_name,
        group_name,
        snapshot_name,
        namespace,
        confirm,
        profile=profile,
    )


def snapshot_rollback(
    pool_name,
    group_name,
    snapshot_name,
    namespace=None,
    confirm=False,
    profile="default",
):
    """Rollback a snapshot. CLI Example: ``salt-call --local ceph_rbd_group.snapshot_rollback rbd group s1 confirm=true``"""
    return _call(
        "snapshot_rollback",
        pool_name,
        group_name,
        snapshot_name,
        namespace,
        confirm,
        profile=profile,
    )
