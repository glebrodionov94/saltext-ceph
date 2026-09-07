"""Manage NFS-Ganesha exports from the salt-ssh controller."""

from saltext.ceph.utils.ceph import nfs_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_nfs"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def clusters(info=False, profile="default"):
    """List NFS clusters."""
    return _invoke(nfs_api.clusters, info, profile)


def list_exports(cluster_id=None, profile="default"):
    """List NFS exports."""
    return _invoke(nfs_api.list_exports, cluster_id, profile)


def get_export(cluster_id, export_id, profile="default"):
    """Return one NFS export."""
    return _invoke(nfs_api.get_export, cluster_id, export_id, profile)


def create_export(
    path,
    cluster_id,
    pseudo,
    access_type,
    squash,
    security_label,
    protocols,
    transports,
    fsal,
    clients,
    profile="default",
):
    """Create a CephFS or RGW export."""
    return _invoke(
        nfs_api.create_export,
        path,
        cluster_id,
        pseudo,
        access_type,
        squash,
        security_label,
        protocols,
        transports,
        fsal,
        clients,
        profile,
    )


def update_export(
    cluster_id,
    export_id,
    path,
    pseudo,
    access_type,
    squash,
    security_label,
    protocols,
    transports,
    fsal,
    clients,
    profile="default",
):
    """Replace the public configuration of an NFS export."""
    return _invoke(
        nfs_api.update_export,
        cluster_id,
        export_id,
        path,
        pseudo,
        access_type,
        squash,
        security_label,
        protocols,
        transports,
        fsal,
        clients,
        profile,
    )


def delete_export(cluster_id, export_id, confirm=False, profile="default"):
    """Remove an NFS export after confirmation."""
    return _invoke(nfs_api.delete_export, cluster_id, export_id, confirm, profile)
