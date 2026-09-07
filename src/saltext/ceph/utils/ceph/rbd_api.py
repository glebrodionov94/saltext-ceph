"""Salt-facing composition for RBD image operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rbd
from saltext.ceph.utils.ceph.errors import ConfigurationError

OPERATIONS = {
    "list": rbd.list_,
    "get": rbd.get,
    "create": rbd.create,
    "update": rbd.update,
    "delete": rbd.delete,
    "copy": rbd.copy,
    "flatten": rbd.flatten,
    "default_features": rbd.default_features,
    "clone_format_version": rbd.clone_format_version,
    "move_to_trash": rbd.move_to_trash,
    "trash_list": rbd.trash_list,
    "trash_purge": rbd.trash_purge,
    "trash_restore": rbd.trash_restore,
    "trash_delete": rbd.trash_delete,
    "namespace_list": rbd.namespace_list,
    "namespace_create": rbd.namespace_create,
    "namespace_delete": rbd.namespace_delete,
    "snapshot_create": rbd.snapshot_create,
    "snapshot_update": rbd.snapshot_update,
    "snapshot_delete": rbd.snapshot_delete,
    "snapshot_rollback": rbd.snapshot_rollback,
    "snapshot_clone": rbd.snapshot_clone,
}


def call(opts, pillar, context, operation, *args, profile="default", **kwargs):
    """Invoke a known RBD operation with one cached profile client."""
    try:
        function = OPERATIONS[operation]
    except KeyError:
        raise ConfigurationError("Unknown RBD operation.") from None
    client = ceph.get_client(opts, pillar, context, profile)
    return function(client, *args, **kwargs).as_dict()
