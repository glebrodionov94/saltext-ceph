"""Salt-facing composition for public NFS Dashboard operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import nfs


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def clusters(opts, pillar, context, info=False, profile="default"):
    """List NFS clusters."""
    return nfs.clusters(_client(opts, pillar, context, profile), info).as_dict()


def list_exports(opts, pillar, context, cluster_id=None, profile="default"):
    """List NFS exports."""
    return nfs.list_exports(_client(opts, pillar, context, profile), cluster_id).as_dict()


def get_export(opts, pillar, context, cluster_id, export_id, profile="default"):
    """Return one NFS export."""
    return nfs.get_export(_client(opts, pillar, context, profile), cluster_id, export_id).as_dict()


def create_export(
    opts,
    pillar,
    context,
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
    """Create an NFS export."""
    return nfs.create_export(
        _client(opts, pillar, context, profile),
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
    ).as_dict()


def update_export(
    opts,
    pillar,
    context,
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
    """Replace an NFS export's public configuration."""
    return nfs.update_export(
        _client(opts, pillar, context, profile),
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
    ).as_dict()


def delete_export(
    opts,
    pillar,
    context,
    cluster_id,
    export_id,
    confirm=False,
    profile="default",
):
    """Remove an NFS export after confirmation."""
    return nfs.delete_export(
        _client(opts, pillar, context, profile), cluster_id, export_id, confirm
    ).as_dict()
