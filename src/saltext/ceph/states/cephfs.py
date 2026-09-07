"""Declaratively manage durable CephFS resources through Dashboard.

Only fields that the public API returns are compared.  Arguments used only
during filesystem creation and mirror peer bootstrap are intentionally not
reported as managed drift after the resource exists.
"""

import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from datetime import timezone
from posixpath import dirname

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import cephfs as cephfs_utils
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "cephfs"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_SCHEDULE_RE = re.compile(r"[1-9][0-9]*[mhdwMy]")
_RETENTION_UNITS = ("n", "m", "h", "d", "w", "M", "y")


def __virtual__():
    required = {
        "cephfs.list",
        "cephfs.create",
        "cephfs.remove",
        "cephfs.root_directory",
        "cephfs.list_directories",
        "cephfs.make_directory",
        "cephfs.remove_directory",
        "cephfs.set_quota",
        "cephfs.create_snapshot",
        "cephfs.remove_snapshot",
        "cephfs.subvolume_list",
        "cephfs.subvolume_create",
        "cephfs.subvolume_resize",
        "cephfs.subvolume_remove",
        "cephfs.snapshot_visibility",
        "cephfs.set_snapshot_visibility",
        "cephfs.group_list",
        "cephfs.group_create",
        "cephfs.group_resize",
        "cephfs.group_remove",
        "cephfs.subvolume_snapshot_list",
        "cephfs.subvolume_snapshot_create",
        "cephfs.subvolume_snapshot_remove",
        "cephfs.schedule_list",
        "cephfs.schedule_create",
        "cephfs.schedule_update",
        "cephfs.schedule_remove",
        "cephfs.schedule_activate",
        "cephfs.schedule_deactivate",
        "cephfs.mirror_peer_list",
        "cephfs.mirror_add_peer",
        "cephfs.mirror_remove_peer",
        "cephfs.mirror_directory_list",
        "cephfs.mirror_add_directory",
        "cephfs.mirror_remove_directory",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _wait(response, profile, task_timeout, task_interval):
    reconcile.wait_if_accepted(
        __salt__,
        response,
        profile=profile,
        timeout=task_timeout,
        interval=task_interval,
    )


def _confirm_type(confirm):
    if not isinstance(confirm, bool):
        raise ConfigurationError("confirm must be a boolean.")


def _path(value):
    value = cephfs_utils.filesystem_path(value)
    if "//" in value:
        raise ConfigurationError("path must not contain repeated separators.")
    return value if value == "/" else value.rstrip("/")


def _filesystem(name, profile):
    items = reconcile.data(
        __salt__["cephfs.list"](profile=profile),
        "CephFS filesystem list",
        expected=list,
    )
    matches = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ProtocolError("CephFS filesystem list returned an unexpected response shape.")
        item_name = item.get("name")
        if not isinstance(item_name, str):
            mdsmap = item.get("mdsmap")
            item_name = mdsmap.get("fs_name") if isinstance(mdsmap, Mapping) else None
        if not isinstance(item_name, str):
            raise ProtocolError("CephFS filesystem list returned an unexpected response shape.")
        if item_name in seen:
            raise ProtocolError("CephFS filesystem list returned duplicate filesystems.")
        seen.add(item_name)
        if item_name == name:
            matches.append({"filesystem": item_name})
    return matches[0] if matches else None


def filesystem_present(
    name,
    service_spec,
    data_pool=None,
    metadata_pool=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a filesystem exists.

    ``service_spec`` and the pool names are create-only because the filesystem
    list does not expose an exact projection of those inputs.
    """
    ret = reconcile.state_result(name)
    try:
        name = cephfs_utils.name(name, "fs_name")
        service_spec = cephfs_utils.options(service_spec)
        if not isinstance(service_spec.get("placement"), Mapping):
            raise ConfigurationError("service_spec requires a placement mapping.")
        if data_pool is not None:
            data_pool = cephfs_utils.name(data_pool, "data_pool")
        if metadata_pool is not None:
            metadata_pool = cephfs_utils.name(metadata_pool, "metadata_pool")
        desired = {"filesystem": name}
        current = _filesystem(name, profile)
        if current == desired:
            return reconcile.no_change(ret, f"CephFS filesystem {name} already exists.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"CephFS filesystem {name} would be created."
            )
        response = __salt__["cephfs.create"](
            name,
            service_spec,
            data_pool=data_pool,
            metadata_pool=metadata_pool,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _filesystem(name, profile)
        if after != desired:
            raise ProtocolError(f"CephFS filesystem {name} did not appear after creation.")
        return reconcile.changed(ret, current, after, f"CephFS filesystem {name} was created.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def filesystem_absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a filesystem is absent; live removal requires ``confirm=True``."""
    ret = reconcile.state_result(name)
    try:
        name = cephfs_utils.name(name, "fs_name")
        _confirm_type(confirm)
        current = _filesystem(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"CephFS filesystem {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"CephFS filesystem {name} would be removed."
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS filesystem requires confirm=True.")
        response = __salt__["cephfs.remove"](name, confirm=True, profile=profile)
        _wait(response, profile, task_timeout, task_interval)
        if _filesystem(name, profile) is not None:
            raise ProtocolError(f"CephFS filesystem {name} still exists after removal.")
        return reconcile.changed(ret, current, None, f"CephFS filesystem {name} was removed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _directory_item(fs_id, path, max_bytes, max_files, profile):
    if path == "/":
        item = reconcile.data(
            __salt__["cephfs.root_directory"](fs_id, profile=profile),
            "CephFS root directory read",
            expected=Mapping,
        )
        items = [item]
    else:
        parent = dirname(path) or "/"
        items = reconcile.data(
            __salt__["cephfs.list_directories"](fs_id, path=parent, depth=1, profile=profile),
            "CephFS directory list",
            expected=list,
        )
    matches = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            raise ProtocolError("CephFS directory list returned an unexpected response shape.")
        item_path = _path(item["path"])
        if item_path in seen:
            raise ProtocolError("CephFS directory list returned duplicate paths.")
        seen.add(item_path)
        if item_path != path:
            continue
        value = {"fs_id": fs_id, "path": path}
        if max_bytes is not None or max_files is not None:
            quotas = item.get("quotas")
            if not isinstance(quotas, Mapping):
                raise ProtocolError("CephFS directory read did not return quota information.")
            if max_bytes is not None:
                value["max_bytes"] = _response_integer(quotas.get("max_bytes"), "max_bytes")
            if max_files is not None:
                value["max_files"] = _response_integer(quotas.get("max_files"), "max_files")
        matches.append(value)
    if len(matches) > 1:
        raise ProtocolError("CephFS directory list returned duplicate paths.")
    return matches[0] if matches else None


def _response_integer(value, label):
    if isinstance(value, bool):
        raise ProtocolError(f"CephFS returned an invalid {label} value.")
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if not isinstance(value, int) or value < 0:
        raise ProtocolError(f"CephFS returned an invalid {label} value.")
    return value


def _quota(value, label):
    if value is None:
        return None
    return cephfs_utils.positive_integer(value, label, allow_zero=True)


def directory_present(
    name,
    fs_id,
    max_bytes=None,
    max_files=None,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a directory exists and optionally manage its exact quotas."""
    ret = reconcile.state_result(name)
    try:
        path = _path(name)
        fs_id = cephfs_utils.identifier(fs_id, "fs_id")
        max_bytes = _quota(max_bytes, "max_bytes")
        max_files = _quota(max_files, "max_files")
        _confirm_type(confirm)
        if path == "/" and (max_bytes is not None or max_files is not None):
            raise ConfigurationError("Dashboard does not expose quota data for the root directory.")
        desired = {"fs_id": fs_id, "path": path}
        if max_bytes is not None:
            desired["max_bytes"] = max_bytes
        if max_files is not None:
            desired["max_files"] = max_files
        current = _directory_item(fs_id, path, max_bytes, max_files, profile)
        if current == desired:
            return reconcile.no_change(ret, f"CephFS directory {path} is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"CephFS directory {path} would be reconciled."
            )
        before = current
        if current is not None:
            reductions = (
                max_bytes is not None
                and max_bytes != 0
                and (current.get("max_bytes") == 0 or max_bytes < current.get("max_bytes"))
            ) or (
                max_files is not None
                and max_files != 0
                and (current.get("max_files") == 0 or max_files < current.get("max_files"))
            )
            if reductions and not confirm:
                raise ConfigurationError("Lowering a CephFS directory quota requires confirm=True.")
        if current is None:
            if path == "/":
                raise ProtocolError("CephFS root directory was not returned by Dashboard.")
            response = __salt__["cephfs.make_directory"](fs_id, path, profile=profile)
            _wait(response, profile, task_timeout, task_interval)
            current = _directory_item(fs_id, path, max_bytes, max_files, profile)
            if current is None:
                raise ProtocolError(f"CephFS directory {path} did not appear after creation.")
        quota_changes = {}
        if max_bytes is not None and current.get("max_bytes") != max_bytes:
            quota_changes["max_bytes"] = max_bytes
        if max_files is not None and current.get("max_files") != max_files:
            quota_changes["max_files"] = max_files
        if quota_changes:
            response = __salt__["cephfs.set_quota"](
                fs_id,
                path,
                max_bytes=quota_changes.get("max_bytes"),
                max_files=quota_changes.get("max_files"),
                profile=profile,
            )
            _wait(response, profile, task_timeout, task_interval)
        after = _directory_item(fs_id, path, max_bytes, max_files, profile)
        if after != desired:
            raise ProtocolError(f"CephFS directory {path} did not converge.")
        return reconcile.changed(ret, before, after, f"CephFS directory {path} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def directory_absent(
    name,
    fs_id,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a non-root CephFS directory is absent."""
    ret = reconcile.state_result(name)
    try:
        path = _path(name)
        fs_id = cephfs_utils.identifier(fs_id, "fs_id")
        _confirm_type(confirm)
        if path == "/":
            raise ConfigurationError("The CephFS root directory cannot be removed.")
        current = _directory_item(fs_id, path, None, None, profile)
        if current is None:
            return reconcile.no_change(ret, f"CephFS directory {path} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"CephFS directory {path} would be removed."
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS directory requires confirm=True.")
        response = __salt__["cephfs.remove_directory"](fs_id, path, confirm=True, profile=profile)
        _wait(response, profile, task_timeout, task_interval)
        if _directory_item(fs_id, path, None, None, profile) is not None:
            raise ProtocolError(f"CephFS directory {path} still exists after removal.")
        return reconcile.changed(ret, current, None, f"CephFS directory {path} was removed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _directory_snapshot(fs_id, path, snapshot, profile):
    item = _directory_item(fs_id, path, None, None, profile)
    if item is None:
        return None, None
    parent = dirname(path) or "/"
    if path == "/":
        raw = reconcile.data(
            __salt__["cephfs.root_directory"](fs_id, profile=profile),
            "CephFS root directory read",
            expected=Mapping,
        )
    else:
        entries = reconcile.data(
            __salt__["cephfs.list_directories"](fs_id, path=parent, depth=1, profile=profile),
            "CephFS directory list",
            expected=list,
        )
        matching = []
        for entry in entries:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
                raise ProtocolError("CephFS directory list changed during snapshot read.")
            if _path(entry["path"]) == path:
                matching.append(entry)
        if len(matching) != 1:
            raise ProtocolError("CephFS directory list changed during snapshot read.")
        raw = matching[0]
    snapshots = raw.get("snapshots")
    if not isinstance(snapshots, list):
        raise ProtocolError("CephFS directory read returned invalid snapshot information.")
    names = []
    for entry in snapshots:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
            raise ProtocolError("CephFS directory read returned invalid snapshot information.")
        names.append(entry["name"])
    if len(set(names)) != len(names):
        raise ProtocolError("CephFS directory read returned duplicate snapshots.")
    current = None
    if snapshot in names:
        current = {"fs_id": fs_id, "path": path, "snapshot": snapshot}
    return item, current


def directory_snapshot_present(
    name,
    fs_id,
    path,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a named directory snapshot exists."""
    ret = reconcile.state_result(name)
    try:
        snapshot = cephfs_utils.name(name, "snapshot_name")
        fs_id = cephfs_utils.identifier(fs_id, "fs_id")
        path = _path(path)
        parent, current = _directory_snapshot(fs_id, path, snapshot, profile)
        if parent is None:
            raise ConfigurationError(f"Parent CephFS directory {path} does not exist.")
        desired = {"fs_id": fs_id, "path": path, "snapshot": snapshot}
        if current == desired:
            return reconcile.no_change(ret, f"CephFS directory snapshot {path}@{snapshot} exists.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                desired,
                f"CephFS directory snapshot {path}@{snapshot} would be created.",
            )
        response = __salt__["cephfs.create_snapshot"](
            fs_id, path, snapshot_name=snapshot, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        _, after = _directory_snapshot(fs_id, path, snapshot, profile)
        if after != desired:
            raise ProtocolError(f"CephFS directory snapshot {path}@{snapshot} did not appear.")
        return reconcile.changed(
            ret, current, after, f"CephFS directory snapshot {path}@{snapshot} was created."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def directory_snapshot_absent(
    name,
    fs_id,
    path,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a named directory snapshot is absent."""
    ret = reconcile.state_result(name)
    try:
        snapshot = cephfs_utils.name(name, "snapshot_name")
        fs_id = cephfs_utils.identifier(fs_id, "fs_id")
        path = _path(path)
        _confirm_type(confirm)
        parent, current = _directory_snapshot(fs_id, path, snapshot, profile)
        if parent is None or current is None:
            return reconcile.no_change(
                ret, f"CephFS directory snapshot {path}@{snapshot} is already absent."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"CephFS directory snapshot {path}@{snapshot} would be removed."
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS directory snapshot requires confirm=True.")
        response = __salt__["cephfs.remove_snapshot"](
            fs_id, path, snapshot, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        _, after = _directory_snapshot(fs_id, path, snapshot, profile)
        if after is not None:
            raise ProtocolError(f"CephFS directory snapshot {path}@{snapshot} still exists.")
        return reconcile.changed(
            ret, current, None, f"CephFS directory snapshot {path}@{snapshot} was removed."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _sized_resource(function, volume, resource_name, size, profile, group_name=None):
    kwargs = {"info": True, "profile": profile}
    if group_name is not None:
        kwargs["group_name"] = group_name
    items = reconcile.data(
        __salt__[function](volume, **kwargs),
        "CephFS volume resource list",
        expected=list,
    )
    matches = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ProtocolError("CephFS volume resource list returned an unexpected shape.")
        item_name = item["name"]
        if item_name in seen:
            raise ProtocolError("CephFS volume resource list returned duplicate names.")
        seen.add(item_name)
        if item_name != resource_name:
            continue
        value = {"volume": volume, "name": resource_name}
        if group_name is not None:
            value["group_name"] = group_name
        if size is not None:
            info = item.get("info")
            if not isinstance(info, Mapping):
                raise ProtocolError("CephFS volume resource did not return info data.")
            quota = info.get("bytes_quota")
            if quota in ("infinite", "inf"):
                value["size"] = None
            else:
                value["size"] = _response_integer(quota, "bytes_quota")
        matches.append(value)
    return matches[0] if matches else None


def _size(value):
    if value is None:
        return None
    return cephfs_utils.positive_integer(value, "size")


def _visibility(volume, subvolume, group_name, profile):
    value = reconcile.data(
        __salt__["cephfs.snapshot_visibility"](
            volume, subvolume, group_name=group_name, profile=profile
        ),
        "CephFS snapshot visibility read",
    )
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise ProtocolError("CephFS snapshot visibility returned an unexpected response shape.")


def subvolume_present(
    name,
    volume,
    group_name=None,
    size=None,
    snapshot_visibility=None,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a subvolume exists and optionally manage quota and visibility.

    Lowering an existing quota, including replacing an unlimited quota, needs
    ``confirm=True``. Snapshot visibility is available only in current Ceph.
    """
    ret = reconcile.state_result(name)
    try:
        name = cephfs_utils.name(name, "subvolume")
        volume = cephfs_utils.name(volume, "volume")
        group_name = (
            None if group_name in (None, "") else cephfs_utils.name(group_name, "group_name")
        )
        size = _size(size)
        _confirm_type(confirm)
        if snapshot_visibility is not None:
            snapshot_visibility = cephfs_utils.boolean(snapshot_visibility, "snapshot_visibility")
        desired = {"volume": volume, "name": name}
        if group_name is not None:
            desired["group_name"] = group_name
        if size is not None:
            desired["size"] = size
        current = _sized_resource(
            "cephfs.subvolume_list", volume, name, size, profile, group_name=group_name
        )
        if current is not None and snapshot_visibility is not None:
            current = dict(current)
            current["snapshot_visibility"] = _visibility(volume, name, group_name, profile)
            desired["snapshot_visibility"] = snapshot_visibility
        elif snapshot_visibility is not None:
            desired["snapshot_visibility"] = snapshot_visibility
        if current == desired:
            return reconcile.no_change(ret, f"CephFS subvolume {volume}/{name} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"CephFS subvolume {volume}/{name} would be reconciled."
            )
        if current is not None and size is not None:
            current_size = current.get("size")
            if (current_size is None or size < current_size) and not confirm:
                raise ConfigurationError("Lowering a CephFS subvolume quota requires confirm=True.")
        before = current
        if current is None:
            options = {}
            if group_name is not None:
                options["group_name"] = group_name
            if size is not None:
                options["size"] = size
            response = __salt__["cephfs.subvolume_create"](
                volume, name, options=options or None, profile=profile
            )
            _wait(response, profile, task_timeout, task_interval)
            current = _sized_resource(
                "cephfs.subvolume_list", volume, name, size, profile, group_name=group_name
            )
            if current is None:
                raise ProtocolError(f"CephFS subvolume {volume}/{name} did not appear.")
        if size is not None and current.get("size") != size:
            response = __salt__["cephfs.subvolume_resize"](
                volume, name, size, group_name=group_name, profile=profile
            )
            _wait(response, profile, task_timeout, task_interval)
        if snapshot_visibility is not None:
            visible = _visibility(volume, name, group_name, profile)
            if visible != snapshot_visibility:
                response = __salt__["cephfs.set_snapshot_visibility"](
                    volume,
                    name,
                    snapshot_visibility,
                    group_name=group_name,
                    profile=profile,
                )
                _wait(response, profile, task_timeout, task_interval)
        after = _sized_resource(
            "cephfs.subvolume_list", volume, name, size, profile, group_name=group_name
        )
        if after is not None and snapshot_visibility is not None:
            after = dict(after)
            after["snapshot_visibility"] = _visibility(volume, name, group_name, profile)
        if after != desired:
            raise ProtocolError(f"CephFS subvolume {volume}/{name} did not converge.")
        return reconcile.changed(
            ret, before, after, f"CephFS subvolume {volume}/{name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def subvolume_absent(
    name,
    volume,
    group_name=None,
    retain_snapshots=False,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a subvolume is absent."""
    ret = reconcile.state_result(name)
    try:
        name = cephfs_utils.name(name, "subvolume")
        volume = cephfs_utils.name(volume, "volume")
        group_name = (
            None if group_name in (None, "") else cephfs_utils.name(group_name, "group_name")
        )
        retain_snapshots = cephfs_utils.boolean(retain_snapshots, "retain_snapshots")
        _confirm_type(confirm)
        current = _sized_resource(
            "cephfs.subvolume_list", volume, name, None, profile, group_name=group_name
        )
        if current is None:
            return reconcile.no_change(ret, f"CephFS subvolume {volume}/{name} is absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"CephFS subvolume {volume}/{name} would be removed."
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS subvolume requires confirm=True.")
        response = __salt__["cephfs.subvolume_remove"](
            volume,
            name,
            group_name=group_name,
            retain_snapshots=retain_snapshots,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        if (
            _sized_resource(
                "cephfs.subvolume_list", volume, name, None, profile, group_name=group_name
            )
            is not None
        ):
            raise ProtocolError(f"CephFS subvolume {volume}/{name} still exists.")
        return reconcile.changed(
            ret, current, None, f"CephFS subvolume {volume}/{name} was removed."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def subvolume_group_present(
    name,
    volume,
    size=None,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a subvolume group exists and optionally manage its byte quota."""
    ret = reconcile.state_result(name)
    try:
        name = cephfs_utils.name(name, "group_name")
        volume = cephfs_utils.name(volume, "volume")
        size = _size(size)
        _confirm_type(confirm)
        desired = {"volume": volume, "name": name}
        if size is not None:
            desired["size"] = size
        current = _sized_resource("cephfs.group_list", volume, name, size, profile)
        if current == desired:
            return reconcile.no_change(ret, f"CephFS subvolume group {volume}/{name} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                desired,
                f"CephFS subvolume group {volume}/{name} would be reconciled.",
            )
        if current is not None and size is not None:
            current_size = current.get("size")
            if (current_size is None or size < current_size) and not confirm:
                raise ConfigurationError("Lowering a CephFS group quota requires confirm=True.")
        before = current
        if current is None:
            options = {"size": size} if size is not None else None
            response = __salt__["cephfs.group_create"](
                volume, name, options=options, profile=profile
            )
            _wait(response, profile, task_timeout, task_interval)
            current = _sized_resource("cephfs.group_list", volume, name, size, profile)
            if current is None:
                raise ProtocolError(f"CephFS subvolume group {volume}/{name} did not appear.")
        if size is not None and current.get("size") != size:
            response = __salt__["cephfs.group_resize"](volume, name, size, profile=profile)
            _wait(response, profile, task_timeout, task_interval)
        after = _sized_resource("cephfs.group_list", volume, name, size, profile)
        if after != desired:
            raise ProtocolError(f"CephFS subvolume group {volume}/{name} did not converge.")
        return reconcile.changed(
            ret, before, after, f"CephFS subvolume group {volume}/{name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def subvolume_group_absent(
    name,
    volume,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a subvolume group is absent."""
    ret = reconcile.state_result(name)
    try:
        name = cephfs_utils.name(name, "group_name")
        volume = cephfs_utils.name(volume, "volume")
        _confirm_type(confirm)
        current = _sized_resource("cephfs.group_list", volume, name, None, profile)
        if current is None:
            return reconcile.no_change(ret, f"CephFS subvolume group {volume}/{name} is absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"CephFS subvolume group {volume}/{name} would be removed."
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS subvolume group requires confirm=True.")
        response = __salt__["cephfs.group_remove"](volume, name, confirm=True, profile=profile)
        _wait(response, profile, task_timeout, task_interval)
        if _sized_resource("cephfs.group_list", volume, name, None, profile) is not None:
            raise ProtocolError(f"CephFS subvolume group {volume}/{name} still exists.")
        return reconcile.changed(
            ret, current, None, f"CephFS subvolume group {volume}/{name} was removed."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _subvolume_snapshot(volume, subvolume, snapshot, group_name, profile):
    items = reconcile.data(
        __salt__["cephfs.subvolume_snapshot_list"](
            volume, subvolume, group_name=group_name, info=False, profile=profile
        ),
        "CephFS subvolume snapshot list",
        expected=list,
    )
    names = []
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ProtocolError("CephFS subvolume snapshot list returned an unexpected shape.")
        names.append(item["name"])
    if len(set(names)) != len(names):
        raise ProtocolError("CephFS subvolume snapshot list returned duplicate names.")
    if snapshot not in names:
        return None
    current = {"volume": volume, "subvolume": subvolume, "snapshot": snapshot}
    if group_name is not None:
        current["group_name"] = group_name
    return current


def subvolume_snapshot_present(
    name,
    volume,
    subvolume,
    group_name=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a named subvolume snapshot exists."""
    ret = reconcile.state_result(name)
    try:
        name = cephfs_utils.name(name, "snapshot")
        volume = cephfs_utils.name(volume, "volume")
        subvolume = cephfs_utils.name(subvolume, "subvolume")
        group_name = (
            None if group_name in (None, "") else cephfs_utils.name(group_name, "group_name")
        )
        desired = {"volume": volume, "subvolume": subvolume, "snapshot": name}
        if group_name is not None:
            desired["group_name"] = group_name
        current = _subvolume_snapshot(volume, subvolume, name, group_name, profile)
        if current == desired:
            return reconcile.no_change(
                ret, f"CephFS subvolume snapshot {volume}/{subvolume}@{name} exists."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                desired,
                f"CephFS subvolume snapshot {volume}/{subvolume}@{name} would be created.",
            )
        response = __salt__["cephfs.subvolume_snapshot_create"](
            volume, subvolume, name, group_name=group_name, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _subvolume_snapshot(volume, subvolume, name, group_name, profile)
        if after != desired:
            raise ProtocolError(
                f"CephFS subvolume snapshot {volume}/{subvolume}@{name} did not appear."
            )
        return reconcile.changed(
            ret,
            current,
            after,
            f"CephFS subvolume snapshot {volume}/{subvolume}@{name} was created.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def subvolume_snapshot_absent(
    name,
    volume,
    subvolume,
    group_name=None,
    force=True,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a named subvolume snapshot is absent."""
    ret = reconcile.state_result(name)
    try:
        name = cephfs_utils.name(name, "snapshot")
        volume = cephfs_utils.name(volume, "volume")
        subvolume = cephfs_utils.name(subvolume, "subvolume")
        group_name = (
            None if group_name in (None, "") else cephfs_utils.name(group_name, "group_name")
        )
        force = cephfs_utils.boolean(force, "force")
        _confirm_type(confirm)
        current = _subvolume_snapshot(volume, subvolume, name, group_name, profile)
        if current is None:
            return reconcile.no_change(
                ret, f"CephFS subvolume snapshot {volume}/{subvolume}@{name} is absent."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                None,
                f"CephFS subvolume snapshot {volume}/{subvolume}@{name} would be removed.",
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS subvolume snapshot requires confirm=True.")
        response = __salt__["cephfs.subvolume_snapshot_remove"](
            volume,
            subvolume,
            name,
            group_name=group_name,
            force=force,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        if _subvolume_snapshot(volume, subvolume, name, group_name, profile) is not None:
            raise ProtocolError(
                f"CephFS subvolume snapshot {volume}/{subvolume}@{name} still exists."
            )
        return reconcile.changed(
            ret,
            current,
            None,
            f"CephFS subvolume snapshot {volume}/{subvolume}@{name} was removed.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _start(value):
    cephfs_utils.text(value, "start")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ConfigurationError("start must be an ISO 8601 timestamp.") from None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(microsecond=0).isoformat(timespec="seconds")


def _schedule(value):
    if not isinstance(value, str) or not _SCHEDULE_RE.fullmatch(value):
        raise ConfigurationError("schedule must use a positive count and m, h, d, w, M, or y.")
    return value


def _retention(value):
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ConfigurationError("retention must be a mapping or null.")
    unknown = set(value).difference(_RETENTION_UNITS)
    if unknown:
        raise ConfigurationError("retention contains an unsupported period.")
    normalized = {}
    for unit, count in value.items():
        normalized[unit] = cephfs_utils.positive_integer(count, f"retention[{unit}]")
    return {unit: normalized[unit] for unit in _RETENTION_UNITS if unit in normalized}


def _retention_arg(value):
    if not value:
        return None
    return "|".join(f"{count}-{unit}" for unit, count in value.items())


def _schedule_item(filesystem, path, schedule, start, retention, active, profile):
    items = reconcile.data(
        __salt__["cephfs.schedule_list"](filesystem, path=path, recursive=False, profile=profile),
        "CephFS snapshot schedule list",
        expected=list,
    )
    matches = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ProtocolError("CephFS snapshot schedule list returned an unexpected shape.")
        item_path = item.get("rel_path", item.get("path"))
        item_start = item.get("start")
        if not isinstance(item_path, str) or not isinstance(item_start, str):
            raise ProtocolError("CephFS snapshot schedule list returned an unexpected shape.")
        try:
            item_start = _start(item_start)
        except ConfigurationError as exc:
            raise ProtocolError("CephFS snapshot schedule returned an invalid timestamp.") from exc
        if (
            item.get("fs") != filesystem
            or _path(item_path) != path
            or item.get("schedule") != schedule
            or item_start != start
            or item.get("subvol") not in (None, "")
            or item.get("group") not in (None, "")
        ):
            continue
        value = {
            "filesystem": filesystem,
            "path": path,
            "schedule": schedule,
            "start": start,
        }
        if retention is not None:
            current_retention = item.get("retention")
            if not isinstance(current_retention, Mapping):
                raise ProtocolError("CephFS snapshot schedule returned invalid retention data.")
            value["retention"] = _retention(current_retention)
        if active is not None:
            current_active = item.get("active")
            if not isinstance(current_active, bool):
                raise ProtocolError("CephFS snapshot schedule returned invalid active state.")
            value["active"] = current_active
        matches.append(value)
    if len(matches) > 1:
        raise ProtocolError("CephFS snapshot schedule list returned a duplicate identity.")
    return matches[0] if matches else None


def snapshot_schedule_present(
    name,
    filesystem,
    schedule,
    start,
    retention=None,
    active=True,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure an ordinary-path snapshot schedule exists with exact policy.

    ``name`` is the absolute path. Subvolume/group-relative schedules are not
    supported because Dashboard cannot list them with an exact scope filter.
    Removing or replacing retention entries needs ``confirm=True``.
    """
    ret = reconcile.state_result(name)
    try:
        path = _path(name)
        filesystem = cephfs_utils.name(filesystem, "filesystem")
        schedule = _schedule(schedule)
        start = _start(start)
        retention = _retention(retention)
        if active is not None:
            active = cephfs_utils.boolean(active, "active")
        _confirm_type(confirm)
        desired = {
            "filesystem": filesystem,
            "path": path,
            "schedule": schedule,
            "start": start,
        }
        if retention is not None:
            desired["retention"] = retention
        if active is not None:
            desired["active"] = active
        current = _schedule_item(filesystem, path, schedule, start, retention, active, profile)
        if current == desired:
            return reconcile.no_change(ret, f"CephFS snapshot schedule for {path} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"CephFS snapshot schedule for {path} would be reconciled."
            )
        before = current
        if current is None:
            response = __salt__["cephfs.schedule_create"](
                filesystem,
                path,
                schedule,
                start,
                retention_policy=_retention_arg(retention),
                subvolume=None,
                group_name=None,
                profile=profile,
            )
            _wait(response, profile, task_timeout, task_interval)
            current = _schedule_item(filesystem, path, schedule, start, retention, active, profile)
            if current is None:
                raise ProtocolError(f"CephFS snapshot schedule for {path} did not appear.")
        if retention is not None and current.get("retention") != retention:
            old = current.get("retention", {})
            removed = {
                unit: count
                for unit, count in old.items()
                if unit not in retention or retention[unit] != count
            }
            added = {
                unit: count
                for unit, count in retention.items()
                if unit not in old or old[unit] != count
            }
            if removed and not confirm:
                raise ConfigurationError(
                    "Removing CephFS snapshot retention requires confirm=True."
                )
            response = __salt__["cephfs.schedule_update"](
                filesystem,
                path,
                retention_to_add=_retention_arg(added),
                retention_to_remove=_retention_arg(removed),
                subvolume=None,
                group_name=None,
                confirm=bool(removed),
                profile=profile,
            )
            _wait(response, profile, task_timeout, task_interval)
        if active is not None:
            refreshed = _schedule_item(
                filesystem, path, schedule, start, retention, active, profile
            )
            if refreshed is None:
                raise ProtocolError(f"CephFS snapshot schedule for {path} disappeared.")
            if refreshed.get("active") != active:
                action = "schedule_activate" if active else "schedule_deactivate"
                response = __salt__[f"cephfs.{action}"](
                    filesystem,
                    path,
                    schedule,
                    start,
                    subvolume=None,
                    group_name=None,
                    profile=profile,
                )
                _wait(response, profile, task_timeout, task_interval)
        after = _schedule_item(filesystem, path, schedule, start, retention, active, profile)
        if after != desired:
            raise ProtocolError(f"CephFS snapshot schedule for {path} did not converge.")
        return reconcile.changed(
            ret, before, after, f"CephFS snapshot schedule for {path} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def snapshot_schedule_absent(
    name,
    filesystem,
    schedule,
    start,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure one exact ordinary-path snapshot schedule is absent."""
    ret = reconcile.state_result(name)
    try:
        path = _path(name)
        filesystem = cephfs_utils.name(filesystem, "filesystem")
        schedule = _schedule(schedule)
        start = _start(start)
        _confirm_type(confirm)
        current = _schedule_item(filesystem, path, schedule, start, {}, None, profile)
        if current is None:
            return reconcile.no_change(ret, f"CephFS snapshot schedule for {path} is absent.")
        current = dict(current)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"CephFS snapshot schedule for {path} would be removed."
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS snapshot schedule requires confirm=True.")
        response = __salt__["cephfs.schedule_remove"](
            filesystem,
            path,
            schedule,
            start,
            retention_policy=_retention_arg(current["retention"]),
            subvolume=None,
            group_name=None,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        if _schedule_item(filesystem, path, schedule, start, None, None, profile) is not None:
            raise ProtocolError(f"CephFS snapshot schedule for {path} still exists.")
        return reconcile.changed(
            ret, current, None, f"CephFS snapshot schedule for {path} was removed."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _mirror_directories(filesystem, profile):
    items = reconcile.data(
        __salt__["cephfs.mirror_directory_list"](filesystem, profile=profile),
        "CephFS mirror directory list",
        expected=list,
    )
    paths = []
    for item in items:
        if not isinstance(item, str):
            raise ProtocolError("CephFS mirror directory list returned an unexpected shape.")
        paths.append(_path(item))
    if len(set(paths)) != len(paths):
        raise ProtocolError("CephFS mirror directory list returned duplicate paths.")
    return paths


def mirror_directory_present(
    name,
    filesystem,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a path is registered for CephFS snapshot mirroring."""
    ret = reconcile.state_result(name)
    try:
        path = _path(name)
        filesystem = cephfs_utils.name(filesystem, "filesystem")
        desired = {"filesystem": filesystem, "path": path}
        current = desired if path in _mirror_directories(filesystem, profile) else None
        if current == desired:
            return reconcile.no_change(ret, f"CephFS mirror directory {path} already exists.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"CephFS mirror directory {path} would be added."
            )
        response = __salt__["cephfs.mirror_add_directory"](filesystem, path, profile=profile)
        _wait(response, profile, task_timeout, task_interval)
        after = desired if path in _mirror_directories(filesystem, profile) else None
        if after != desired:
            raise ProtocolError(f"CephFS mirror directory {path} did not appear.")
        return reconcile.changed(ret, current, after, f"CephFS mirror directory {path} was added.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def mirror_directory_absent(
    name,
    filesystem,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a path is not registered for CephFS snapshot mirroring."""
    ret = reconcile.state_result(name)
    try:
        path = _path(name)
        filesystem = cephfs_utils.name(filesystem, "filesystem")
        _confirm_type(confirm)
        current = (
            {"filesystem": filesystem, "path": path}
            if path in _mirror_directories(filesystem, profile)
            else None
        )
        if current is None:
            return reconcile.no_change(ret, f"CephFS mirror directory {path} is absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"CephFS mirror directory {path} would be removed."
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS mirror directory requires confirm=True.")
        response = __salt__["cephfs.mirror_remove_directory"](
            filesystem, path, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        if path in _mirror_directories(filesystem, profile):
            raise ProtocolError(f"CephFS mirror directory {path} still exists.")
        return reconcile.changed(ret, current, None, f"CephFS mirror directory {path} was removed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _mirror_peer(filesystem, site_name, client_name, remote_filesystem, profile):
    items = reconcile.data(
        __salt__["cephfs.mirror_peer_list"](filesystem, profile=profile),
        "CephFS mirror peer list",
        expected=list,
    )
    matches = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping) or len(item) != 1:
            raise ProtocolError("CephFS mirror peer list returned an unexpected shape.")
        peer_uuid, remote = next(iter(item.items()))
        if not isinstance(peer_uuid, str) or not isinstance(remote, Mapping):
            raise ProtocolError("CephFS mirror peer list returned an unexpected shape.")
        try:
            peer_uuid = str(uuid.UUID(peer_uuid))
        except ValueError as exc:
            raise ProtocolError("CephFS mirror peer list returned an invalid UUID.") from exc
        if peer_uuid in seen:
            raise ProtocolError("CephFS mirror peer list returned duplicate UUIDs.")
        seen.add(peer_uuid)
        remote_site = remote.get("site_name", remote.get("cluster_name"))
        if not isinstance(remote_site, str):
            raise ProtocolError("CephFS mirror peer list omitted its site name.")
        if remote_site != site_name:
            continue
        value = {"filesystem": filesystem, "site_name": site_name}
        if client_name is not None:
            value["client_name"] = remote.get("client_name")
        if remote_filesystem is not None:
            value["remote_filesystem"] = remote.get("fs_name")
        matches.append((peer_uuid, value))
    if len(matches) > 1:
        raise ProtocolError("CephFS mirror peer site name is not unique.")
    return matches[0] if matches else (None, None)


def mirror_peer_present(
    name,
    filesystem,
    source=None,
    client_name=None,
    remote_filesystem=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a uniquely named remote mirror peer exists.

    ``source`` is a controller-local bootstrap token file and is read only when
    the peer is absent. Dashboard exposes no token fingerprint, so it is not a
    managed field and is never included in state output.
    """
    ret = reconcile.state_result(name)
    try:
        site_name = cephfs_utils.name(name, "site_name")
        filesystem = cephfs_utils.name(filesystem, "filesystem")
        if client_name is not None:
            client_name = cephfs_utils.text(client_name, "client_name")
        if remote_filesystem is not None:
            remote_filesystem = cephfs_utils.name(remote_filesystem, "remote_filesystem")
        desired = {"filesystem": filesystem, "site_name": site_name}
        if client_name is not None:
            desired["client_name"] = client_name
        if remote_filesystem is not None:
            desired["remote_filesystem"] = remote_filesystem
        _, current = _mirror_peer(filesystem, site_name, client_name, remote_filesystem, profile)
        if current == desired:
            return reconcile.no_change(ret, f"CephFS mirror peer {site_name} already exists.")
        if current is not None:
            raise ConfigurationError(
                f"CephFS mirror peer {site_name} has create-only public-field drift."
            )
        if source is None:
            raise ConfigurationError("source is required when creating a CephFS mirror peer.")
        if __opts__.get("test", False):
            secret_file.read(source)
            return reconcile.planned(
                ret, None, desired, f"CephFS mirror peer {site_name} would be imported."
            )
        response = __salt__["cephfs.mirror_add_peer"](filesystem, source, profile=profile)
        _wait(response, profile, task_timeout, task_interval)
        _, after = _mirror_peer(filesystem, site_name, client_name, remote_filesystem, profile)
        if after != desired:
            raise ProtocolError(f"CephFS mirror peer {site_name} did not converge after import.")
        return reconcile.changed(
            ret, current, after, f"CephFS mirror peer {site_name} was imported."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def mirror_peer_absent(
    name,
    filesystem,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a uniquely named remote mirror peer is absent."""
    ret = reconcile.state_result(name)
    try:
        site_name = cephfs_utils.name(name, "site_name")
        filesystem = cephfs_utils.name(filesystem, "filesystem")
        _confirm_type(confirm)
        peer_uuid, current = _mirror_peer(filesystem, site_name, None, None, profile)
        if current is None:
            return reconcile.no_change(ret, f"CephFS mirror peer {site_name} is absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"CephFS mirror peer {site_name} would be removed."
            )
        if not confirm:
            raise ConfigurationError("Removing a CephFS mirror peer requires confirm=True.")
        response = __salt__["cephfs.mirror_remove_peer"](
            filesystem, peer_uuid, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        _, after = _mirror_peer(filesystem, site_name, None, None, profile)
        if after is not None:
            raise ProtocolError(f"CephFS mirror peer {site_name} still exists.")
        return reconcile.changed(ret, current, None, f"CephFS mirror peer {site_name} was removed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
