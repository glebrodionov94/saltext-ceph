"""Manage NFS-Ganesha exports through the Ceph Dashboard REST API."""

from saltext.ceph.utils.ceph import nfs_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_nfs"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, *args)


def clusters(info=False, profile="default"):
    """List NFS clusters; ``info=true`` needs a current post-Reef Ceph release.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_nfs.clusters
    """
    return _invoke(nfs_api.clusters, info, profile)


def list_exports(cluster_id=None, profile="default"):
    """List exports, optionally filtered by cluster on current Ceph releases.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_nfs.list_exports cluster_id=nfs1
    """
    return _invoke(nfs_api.list_exports, cluster_id, profile)


def get_export(cluster_id, export_id, profile="default"):
    """Return one NFS export.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_nfs.get_export nfs1 1
    """
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
    """Create a CephFS or RGW export from structured values.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_nfs.create_export / nfs1 /cephfs RW root_squash \\
          false '[4]' '["TCP"]' '{"name":"CEPH","fs_name":"cephfs"}' '[]'
    """
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
    """Replace the public configuration of an NFS export.

    Submit the complete export returned by :func:`get_export`, excluding its
    ``cluster_id`` and ``export_id`` fields.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_nfs.update_export nfs1 1 / /cephfs RW \\
          root_squash false '[4]' '["TCP"]' \\
          '{"name":"CEPH","fs_name":"cephfs"}' '[]'
    """
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
    """Remove an export; requires ``confirm=true`` and leaves backing data intact.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_nfs.delete_export nfs1 1 confirm=true
    """
    return _invoke(nfs_api.delete_export, cluster_id, export_id, confirm, profile)
