"""Salt-facing composition for current-Ceph RBD group operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rbd_group
from saltext.ceph.utils.ceph.errors import ConfigurationError

OPERATIONS = {
    "list": rbd_group.list_,
    "get": rbd_group.get,
    "create": rbd_group.create,
    "update": rbd_group.update,
    "delete": rbd_group.delete,
    "add_image": rbd_group.add_image,
    "remove_image": rbd_group.remove_image,
    "snapshot_list": rbd_group.snapshot_list,
    "snapshot_get": rbd_group.snapshot_get,
    "snapshot_create": rbd_group.snapshot_create,
    "snapshot_update": rbd_group.snapshot_update,
    "snapshot_delete": rbd_group.snapshot_delete,
    "snapshot_rollback": rbd_group.snapshot_rollback,
}


def call(opts, pillar, context, operation, *args, profile="default", **kwargs):
    """Invoke a known RBD group operation with one cached profile client."""
    try:
        function = OPERATIONS[operation]
    except KeyError:
        raise ConfigurationError("Unknown RBD group operation.") from None
    client = ceph.get_client(opts, pillar, context, profile)
    return function(client, *args, **kwargs).as_dict()
