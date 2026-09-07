"""Salt-facing composition for the public Dashboard ``cephfs.py`` API."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import cephfs
from saltext.ceph.utils.ceph import cephfs_mirror
from saltext.ceph.utils.ceph import cephfs_schedule
from saltext.ceph.utils.ceph import cephfs_volumes
from saltext.ceph.utils.ceph import local_file
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import ConfigurationError

OPERATIONS = {
    "list": cephfs.list_,
    "create": cephfs.create,
    "remove": cephfs.remove,
    "rename": cephfs.rename,
    "authorize": cephfs.authorize,
    "get": cephfs.get,
    "clients": cephfs.clients,
    "evict_client": cephfs.evict_client,
    "mds_counters": cephfs.mds_counters,
    "root_directory": cephfs.root_directory,
    "list_directories": cephfs.list_directories,
    "make_directory": cephfs.make_directory,
    "remove_directory": cephfs.remove_directory,
    "get_quota": cephfs.get_quota,
    "set_quota": cephfs.set_quota,
    "unlink": cephfs.unlink,
    "statfs": cephfs.statfs,
    "create_snapshot": cephfs.create_snapshot,
    "remove_snapshot": cephfs.remove_snapshot,
    "rename_path": cephfs.rename_path,
    "subvolume_list": cephfs_volumes.subvolume_list,
    "subvolume_info": cephfs_volumes.subvolume_info,
    "subvolume_create": cephfs_volumes.subvolume_create,
    "subvolume_resize": cephfs_volumes.subvolume_resize,
    "subvolume_remove": cephfs_volumes.subvolume_remove,
    "subvolume_exists": cephfs_volumes.subvolume_exists,
    "snapshot_visibility": cephfs_volumes.snapshot_visibility,
    "set_snapshot_visibility": cephfs_volumes.set_snapshot_visibility,
    "group_list": cephfs_volumes.group_list,
    "group_info": cephfs_volumes.group_info,
    "group_create": cephfs_volumes.group_create,
    "group_resize": cephfs_volumes.group_resize,
    "group_remove": cephfs_volumes.group_remove,
    "subvolume_snapshot_list": cephfs_volumes.snapshot_list,
    "subvolume_snapshot_info": cephfs_volumes.snapshot_info,
    "subvolume_snapshot_create": cephfs_volumes.snapshot_create,
    "subvolume_snapshot_remove": cephfs_volumes.snapshot_remove,
    "subvolume_snapshot_clone": cephfs_volumes.snapshot_clone,
    "schedule_list": cephfs_schedule.list_,
    "schedule_create": cephfs_schedule.create,
    "schedule_update": cephfs_schedule.update,
    "schedule_remove": cephfs_schedule.remove,
    "schedule_activate": cephfs_schedule.activate,
    "schedule_deactivate": cephfs_schedule.deactivate,
    "mirror_peer_list": cephfs_mirror.peer_list,
    "mirror_enable": cephfs_mirror.enable,
    "mirror_disable": cephfs_mirror.disable,
    "mirror_remove_peer": cephfs_mirror.remove_peer,
    "mirror_add_directory": cephfs_mirror.add_directory,
    "mirror_remove_directory": cephfs_mirror.remove_directory,
    "mirror_directory_list": cephfs_mirror.directory_list,
    "mirror_checkpoint_list": cephfs_mirror.checkpoint_list,
    "mirror_add_checkpoint": cephfs_mirror.add_checkpoint,
    "mirror_checkpoint_now": cephfs_mirror.checkpoint_now,
    "mirror_remove_checkpoint": cephfs_mirror.remove_checkpoint,
    "mirror_daemon_status": cephfs_mirror.daemon_status,
    "mirror_status": cephfs_mirror.status,
}


def call(opts, pillar, context, operation, *args, profile="default", **kwargs):
    """Invoke a known CephFS operation through one cached profile client."""
    try:
        function = OPERATIONS[operation]
    except KeyError:
        raise ConfigurationError("Unknown CephFS operation.") from None
    client = ceph.get_client(opts, pillar, context, profile)
    return function(client, *args, **kwargs).as_dict()


def write_file(
    opts,
    pillar,
    context,
    fs_id,
    path,
    source,
    confirm=False,
    profile="default",
):
    """Write a controller-local file into CephFS without embedding it in CLI arguments."""
    cephfs.confirmed(confirm, "Writing or replacing a CephFS file")
    contents = local_file.read_text(source)
    client = ceph.get_client(opts, pillar, context, profile)
    response = cephfs.write_file(client, fs_id, path, contents, confirm=True)
    return {
        "status": response.status,
        "data": {"path": path, "source": str(source)},
        "headers": response.headers,
    }


def mirror_create_token(
    opts,
    pillar,
    context,
    filesystem,
    client_name,
    site_name,
    destination,
    overwrite=False,
    profile="default",
):
    """Create a bootstrap token and save it without returning the token to Salt."""
    client = ceph.get_client(opts, pillar, context, profile)
    response = cephfs_mirror.create_token(client, filesystem, client_name, site_name)
    path = secret_file.write(destination, response.data["token"], overwrite=overwrite)
    return {
        "status": response.status,
        "data": {"filesystem": filesystem, "destination": path},
        "headers": response.headers,
    }


def mirror_add_peer(opts, pillar, context, filesystem, source, profile="default"):
    """Import a controller-local bootstrap token without returning it to Salt."""
    token = secret_file.read(source)
    client = ceph.get_client(opts, pillar, context, profile)
    response = cephfs_mirror.add_peer(client, filesystem, token)
    return {
        "status": response.status,
        "data": {"filesystem": filesystem, "source": str(source)},
        "headers": response.headers,
    }
