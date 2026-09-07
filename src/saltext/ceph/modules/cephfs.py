"""Manage CephFS through the public Ceph Dashboard REST API.

The module covers the public controllers defined in Dashboard ``cephfs.py``.
Snapshot visibility and mirroring require a Ceph release that exposes those
endpoints. Mutating execution functions do not reconcile desired state.
"""

from saltext.ceph.utils.ceph import cephfs_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "cephfs"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _call(operation, *args, profile="default", **kwargs):
    return salt_adapter.invoke(
        cephfs_api.call,
        __opts__,
        __pillar__,
        __context__,
        operation,
        *args,
        profile=profile,
        **kwargs,
    )


def list_(profile="default"):
    """List CephFS volumes. CLI Example: ``salt-call --local cephfs.list``"""
    return _call("list", profile=profile)


def create(fs_name, service_spec, data_pool=None, metadata_pool=None, profile="default"):
    """Create a volume. CLI Example: ``salt-call --local cephfs.create fs '{placement: {}}'``"""
    return _call("create", fs_name, service_spec, data_pool, metadata_pool, profile=profile)


def remove(fs_name, confirm=False, profile="default"):
    """Remove a volume. CLI Example: ``salt-call --local cephfs.remove archive confirm=true``"""
    return _call("remove", fs_name, confirm, profile=profile)


def rename(fs_name, new_name, confirm=False, profile="default"):
    """Rename a volume. CLI Example: ``salt-call --local cephfs.rename old new confirm=true``"""
    return _call("rename", fs_name, new_name, confirm, profile=profile)


def authorize(fs_name, client_id, caps, root_squash=False, profile="default"):
    """Set client caps. CLI Example: ``salt-call --local cephfs.authorize fs client.a '[/,rw]'``"""
    return _call("authorize", fs_name, client_id, caps, root_squash, profile=profile)


def get(fs_id, profile="default"):
    """Return filesystem status. CLI Example: ``salt-call --local cephfs.get 1``"""
    return _call("get", fs_id, profile=profile)


def clients(fs_id, profile="default"):
    """List clients. CLI Example: ``salt-call --local cephfs.clients 1``"""
    return _call("clients", fs_id, profile=profile)


def evict_client(fs_id, client_id, confirm=False, profile="default"):
    """Evict a client. CLI Example: ``salt-call --local cephfs.evict_client 1 42 confirm=true``"""
    return _call("evict_client", fs_id, client_id, confirm, profile=profile)


def mds_counters(fs_id, counters=None, profile="default"):
    """Read MDS counters. CLI Example: ``salt-call --local cephfs.mds_counters 1``"""
    return _call("mds_counters", fs_id, counters, profile=profile)


def root_directory(fs_id, profile="default"):
    """Return root metadata. CLI Example: ``salt-call --local cephfs.root_directory 1``"""
    return _call("root_directory", fs_id, profile=profile)


def list_directories(fs_id, path=None, depth=1, profile="default"):
    """List directories. CLI Example: ``salt-call --local cephfs.list_directories 1 / 2``"""
    return _call("list_directories", fs_id, path, depth, profile=profile)


def make_directory(fs_id, path, profile="default"):
    """Create a tree. CLI Example: ``salt-call --local cephfs.make_directory 1 /archive``"""
    return _call("make_directory", fs_id, path, profile=profile)


def remove_directory(fs_id, path, confirm=False, profile="default"):
    """Remove a tree. CLI Example: ``salt-call --local cephfs.remove_directory 1 /archive confirm=true``"""
    return _call("remove_directory", fs_id, path, confirm, profile=profile)


def get_quota(fs_id, path, profile="default"):
    """Read quota. CLI Example: ``salt-call --local cephfs.get_quota 1 /archive``"""
    return _call("get_quota", fs_id, path, profile=profile)


def set_quota(fs_id, path, max_bytes=None, max_files=None, profile="default"):
    """Set quota. CLI Example: ``salt-call --local cephfs.set_quota 1 /archive 1048576``"""
    return _call("set_quota", fs_id, path, max_bytes, max_files, profile=profile)


def write_file(fs_id, path, source, confirm=False, profile="default"):
    """Write a local file. CLI Example: ``salt-call --local cephfs.write_file 1 /a /tmp/a confirm=true``"""
    return salt_adapter.invoke(
        cephfs_api.write_file,
        __opts__,
        __pillar__,
        __context__,
        fs_id,
        path,
        source,
        confirm,
        profile,
    )


def unlink(fs_id, path, confirm=False, profile="default"):
    """Remove a file. CLI Example: ``salt-call --local cephfs.unlink 1 /archive/file confirm=true``"""
    return _call("unlink", fs_id, path, confirm, profile=profile)


def statfs(fs_id, path, profile="default"):
    """Read capacity. CLI Example: ``salt-call --local cephfs.statfs 1 /archive``"""
    return _call("statfs", fs_id, path, profile=profile)


def create_snapshot(fs_id, path, snapshot_name=None, profile="default"):
    """Create a snapshot. CLI Example: ``salt-call --local cephfs.create_snapshot 1 / a``"""
    return _call("create_snapshot", fs_id, path, snapshot_name, profile=profile)


def remove_snapshot(fs_id, path, snapshot_name, confirm=False, profile="default"):
    """Remove a snapshot. CLI Example: ``salt-call --local cephfs.remove_snapshot 1 / a confirm=true``"""
    return _call("remove_snapshot", fs_id, path, snapshot_name, confirm, profile=profile)


def rename_path(fs_id, source, destination, confirm=False, profile="default"):
    """Move a path. CLI Example: ``salt-call --local cephfs.rename_path 1 /old /new confirm=true``"""
    return _call("rename_path", fs_id, source, destination, confirm, profile=profile)


def subvolume_list(volume, group_name=None, info=True, profile="default"):
    """List subvolumes. CLI Example: ``salt-call --local cephfs.subvolume_list fs``"""
    return _call("subvolume_list", volume, group_name, info, profile=profile)


def subvolume_info(volume, subvolume, group_name=None, profile="default"):
    """Read a subvolume. CLI Example: ``salt-call --local cephfs.subvolume_info fs data``"""
    return _call("subvolume_info", volume, subvolume, group_name, profile=profile)


def subvolume_create(volume, subvolume, options=None, profile="default"):
    """Create a subvolume. CLI Example: ``salt-call --local cephfs.subvolume_create fs data``"""
    return _call("subvolume_create", volume, subvolume, options, profile=profile)


def subvolume_resize(volume, subvolume, size, group_name=None, profile="default"):
    """Resize a subvolume. CLI Example: ``salt-call --local cephfs.subvolume_resize fs data 1G``"""
    return _call("subvolume_resize", volume, subvolume, size, group_name, profile=profile)


def subvolume_remove(
    volume,
    subvolume,
    group_name=None,
    retain_snapshots=False,
    confirm=False,
    profile="default",
):
    """Remove a subvolume. CLI Example: ``salt-call --local cephfs.subvolume_remove fs data confirm=true``"""
    return _call(
        "subvolume_remove",
        volume,
        subvolume,
        group_name,
        retain_snapshots,
        confirm,
        profile=profile,
    )


def subvolume_exists(volume, group_name=None, profile="default"):
    """Check subvolumes. CLI Example: ``salt-call --local cephfs.subvolume_exists fs``"""
    return _call("subvolume_exists", volume, group_name, profile=profile)


def snapshot_visibility(volume, subvolume, group_name=None, profile="default"):
    """Read visibility. CLI Example: ``salt-call --local cephfs.snapshot_visibility fs data``"""
    return _call("snapshot_visibility", volume, subvolume, group_name, profile=profile)


def set_snapshot_visibility(volume, subvolume, value, group_name=None, profile="default"):
    """Set visibility. CLI Example: ``salt-call --local cephfs.set_snapshot_visibility fs data visible``"""
    return _call("set_snapshot_visibility", volume, subvolume, value, group_name, profile=profile)


def group_list(volume, info=True, profile="default"):
    """List groups. CLI Example: ``salt-call --local cephfs.group_list fs``"""
    return _call("group_list", volume, info, profile=profile)


def group_info(volume, group_name, profile="default"):
    """Read a group. CLI Example: ``salt-call --local cephfs.group_info fs nightly``"""
    return _call("group_info", volume, group_name, profile=profile)


def group_create(volume, group_name, options=None, profile="default"):
    """Create a group. CLI Example: ``salt-call --local cephfs.group_create fs nightly``"""
    return _call("group_create", volume, group_name, options, profile=profile)


def group_resize(volume, group_name, size, profile="default"):
    """Resize a group. CLI Example: ``salt-call --local cephfs.group_resize fs nightly 10G``"""
    return _call("group_resize", volume, group_name, size, profile=profile)


def group_remove(volume, group_name, confirm=False, profile="default"):
    """Remove a group. CLI Example: ``salt-call --local cephfs.group_remove fs nightly confirm=true``"""
    return _call("group_remove", volume, group_name, confirm, profile=profile)


def subvolume_snapshot_list(volume, subvolume, group_name=None, info=True, profile="default"):
    """List snapshots. CLI Example: ``salt-call --local cephfs.subvolume_snapshot_list fs data``"""
    return _call("subvolume_snapshot_list", volume, subvolume, group_name, info, profile=profile)


def subvolume_snapshot_info(volume, subvolume, snapshot, group_name=None, profile="default"):
    """Read a snapshot. CLI Example: ``salt-call --local cephfs.subvolume_snapshot_info fs data s1``"""
    return _call(
        "subvolume_snapshot_info", volume, subvolume, snapshot, group_name, profile=profile
    )


def subvolume_snapshot_create(volume, subvolume, snapshot, group_name=None, profile="default"):
    """Create a snapshot. CLI Example: ``salt-call --local cephfs.subvolume_snapshot_create fs data s1``"""
    return _call(
        "subvolume_snapshot_create", volume, subvolume, snapshot, group_name, profile=profile
    )


def subvolume_snapshot_remove(
    volume,
    subvolume,
    snapshot,
    group_name=None,
    force=True,
    confirm=False,
    profile="default",
):
    """Remove a snapshot. CLI Example: ``salt-call --local cephfs.subvolume_snapshot_remove fs data s1 confirm=true``"""
    return _call(
        "subvolume_snapshot_remove",
        volume,
        subvolume,
        snapshot,
        group_name,
        force,
        confirm,
        profile=profile,
    )


def subvolume_snapshot_clone(
    volume,
    subvolume,
    snapshot,
    clone,
    group_name=None,
    target_group_name=None,
    profile="default",
):
    """Clone a snapshot. CLI Example: ``salt-call --local cephfs.subvolume_snapshot_clone fs data s1 clone``"""
    return _call(
        "subvolume_snapshot_clone",
        volume,
        subvolume,
        snapshot,
        clone,
        group_name,
        target_group_name,
        profile=profile,
    )


def schedule_list(filesystem, path="/", recursive=True, profile="default"):
    """List schedules. CLI Example: ``salt-call --local cephfs.schedule_list fs /``"""
    return _call("schedule_list", filesystem, path, recursive, profile=profile)


def schedule_create(
    filesystem,
    path,
    schedule,
    start,
    retention_policy=None,
    subvolume=None,
    group_name=None,
    profile="default",
):
    """Create a schedule. CLI Example: ``salt-call --local cephfs.schedule_create fs / 1h 2026-01-01T00:00:00``"""
    return _call(
        "schedule_create",
        filesystem,
        path,
        schedule,
        start,
        retention_policy,
        subvolume,
        group_name,
        profile=profile,
    )


def schedule_update(
    filesystem,
    path,
    retention_to_add=None,
    retention_to_remove=None,
    subvolume=None,
    group_name=None,
    confirm=False,
    profile="default",
):
    """Edit retention. CLI Example: ``salt-call --local cephfs.schedule_update fs / 7-d``"""
    return _call(
        "schedule_update",
        filesystem,
        path,
        retention_to_add,
        retention_to_remove,
        subvolume,
        group_name,
        confirm,
        profile=profile,
    )


def schedule_remove(
    filesystem,
    path,
    schedule,
    start,
    retention_policy=None,
    subvolume=None,
    group_name=None,
    confirm=False,
    profile="default",
):
    """Remove a schedule. CLI Example: ``salt-call --local cephfs.schedule_remove fs / 1h 2026-01-01T00:00:00 confirm=true``"""
    return _call(
        "schedule_remove",
        filesystem,
        path,
        schedule,
        start,
        retention_policy,
        subvolume,
        group_name,
        confirm,
        profile=profile,
    )


def schedule_activate(
    filesystem, path, schedule, start, subvolume=None, group_name=None, profile="default"
):
    """Activate a schedule. CLI Example: ``salt-call --local cephfs.schedule_activate fs / 1h 2026-01-01T00:00:00``"""
    return _call(
        "schedule_activate",
        filesystem,
        path,
        schedule,
        start,
        subvolume,
        group_name,
        profile=profile,
    )


def schedule_deactivate(
    filesystem, path, schedule, start, subvolume=None, group_name=None, profile="default"
):
    """Deactivate a schedule. CLI Example: ``salt-call --local cephfs.schedule_deactivate fs / 1h 2026-01-01T00:00:00``"""
    return _call(
        "schedule_deactivate",
        filesystem,
        path,
        schedule,
        start,
        subvolume,
        group_name,
        profile=profile,
    )


def mirror_peer_list(filesystem, profile="default"):
    """List mirror peers. CLI Example: ``salt-call --local cephfs.mirror_peer_list fs``"""
    return _call("mirror_peer_list", filesystem, profile=profile)


def mirror_enable(filesystem, profile="default"):
    """Enable mirroring. CLI Example: ``salt-call --local cephfs.mirror_enable fs``"""
    return _call("mirror_enable", filesystem, profile=profile)


def mirror_disable(filesystem, confirm=False, profile="default"):
    """Disable mirroring. CLI Example: ``salt-call --local cephfs.mirror_disable fs confirm=true``"""
    return _call("mirror_disable", filesystem, confirm, profile=profile)


def mirror_create_token(
    filesystem,
    client_name,
    site_name,
    destination,
    overwrite=False,
    profile="default",
):
    """Save a token. CLI Example: ``salt-call --local cephfs.mirror_create_token fs client.mirror remote /tmp/token``"""
    return salt_adapter.invoke(
        cephfs_api.mirror_create_token,
        __opts__,
        __pillar__,
        __context__,
        filesystem,
        client_name,
        site_name,
        destination,
        overwrite,
        profile,
    )


def mirror_add_peer(filesystem, source, profile="default"):
    """Add a peer. CLI Example: ``salt-call --local cephfs.mirror_add_peer fs /tmp/token``"""
    return salt_adapter.invoke(
        cephfs_api.mirror_add_peer,
        __opts__,
        __pillar__,
        __context__,
        filesystem,
        source,
        profile,
    )


def mirror_remove_peer(filesystem, peer_uuid, confirm=False, profile="default"):
    """Remove a peer. CLI Example: ``salt-call --local cephfs.mirror_remove_peer fs UUID confirm=true``"""
    return _call("mirror_remove_peer", filesystem, peer_uuid, confirm, profile=profile)


def mirror_add_directory(filesystem, path, profile="default"):
    """Mirror a path. CLI Example: ``salt-call --local cephfs.mirror_add_directory fs /data``"""
    return _call("mirror_add_directory", filesystem, path, profile=profile)


def mirror_remove_directory(filesystem, path, confirm=False, profile="default"):
    """Unmirror a path. CLI Example: ``salt-call --local cephfs.mirror_remove_directory fs /data confirm=true``"""
    return _call("mirror_remove_directory", filesystem, path, confirm, profile=profile)


def mirror_directory_list(filesystem, profile="default"):
    """List mirror paths. CLI Example: ``salt-call --local cephfs.mirror_directory_list fs``"""
    return _call("mirror_directory_list", filesystem, profile=profile)


def mirror_checkpoint_list(filesystem, path, profile="default"):
    """List checkpoints. CLI Example: ``salt-call --local cephfs.mirror_checkpoint_list fs /data``"""
    return _call("mirror_checkpoint_list", filesystem, path, profile=profile)


def mirror_add_checkpoint(filesystem, path, snapshot, profile="default"):
    """Add a checkpoint. CLI Example: ``salt-call --local cephfs.mirror_add_checkpoint fs /data s1``"""
    return _call("mirror_add_checkpoint", filesystem, path, snapshot, profile=profile)


def mirror_checkpoint_now(filesystem, path, profile="default"):
    """Checkpoint now. CLI Example: ``salt-call --local cephfs.mirror_checkpoint_now fs /data``"""
    return _call("mirror_checkpoint_now", filesystem, path, profile=profile)


def mirror_remove_checkpoint(filesystem, path, snapshot, confirm=False, profile="default"):
    """Remove a checkpoint. CLI Example: ``salt-call --local cephfs.mirror_remove_checkpoint fs /data s1 confirm=true``"""
    return _call(
        "mirror_remove_checkpoint",
        filesystem,
        path,
        snapshot,
        confirm,
        profile=profile,
    )


def mirror_daemon_status(profile="default"):
    """Read daemon status. CLI Example: ``salt-call --local cephfs.mirror_daemon_status``"""
    return _call("mirror_daemon_status", profile=profile)


def mirror_status(filesystem, path=None, peer_uuid=None, profile="default"):
    """Read mirror status. CLI Example: ``salt-call --local cephfs.mirror_status fs``"""
    return _call("mirror_status", filesystem, path, peer_uuid, profile=profile)
