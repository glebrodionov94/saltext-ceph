"""CephFS snapshot schedule operations from Dashboard ``cephfs.py``."""

import re
from datetime import datetime

from saltext.ceph.utils.ceph import cephfs
from saltext.ceph.utils.ceph.errors import ConfigurationError

API_VERSION = cephfs.API_VERSION
RESOURCE_PATH = "/api/cephfs/snapshot/schedule"
_SCHEDULE_PATTERN = re.compile(r"[1-9][0-9]*[mhdwMy]")
_RETENTION_PATTERN = re.compile(r"[1-9][0-9]*-[nmhdwMy]")


def _optional_name(value, label):
    return None if value in (None, "") else cephfs.name(value, label)


def _retention(value, label):
    if value is None:
        return None
    cephfs.text(value, label)
    parts = value.split("|")
    if any(not _RETENTION_PATTERN.fullmatch(part) for part in parts):
        raise ConfigurationError(f"{label} must use count-period entries separated by '|'.")
    return value


def _schedule(value):
    if not isinstance(value, str) or not _SCHEDULE_PATTERN.fullmatch(value):
        raise ConfigurationError("schedule must use a positive count and m, h, d, w, M, or y.")
    return value


def _start(value):
    cephfs.text(value, "start")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ConfigurationError("start must be an ISO 8601 timestamp.") from None
    return value


def _route(filesystem, path):
    filesystem = cephfs.route_name(filesystem, "filesystem")
    path = cephfs.route_filesystem_path(path)
    return f"{RESOURCE_PATH}/{filesystem}/{path}"


def list_(client, filesystem, path="/", recursive=True):
    filesystem = cephfs.route_name(filesystem, "filesystem")
    params = {
        "path": cephfs.filesystem_path(path),
        "recursive": cephfs.boolean(recursive, "recursive"),
    }
    return client.request(
        "GET", f"{RESOURCE_PATH}/{filesystem}", api_version=API_VERSION, params=params
    )


def create(
    client,
    filesystem,
    path,
    schedule,
    start,
    retention_policy=None,
    subvolume=None,
    group_name=None,
):
    data = cephfs.optional_params(
        fs=cephfs.name(filesystem, "filesystem"),
        path=cephfs.filesystem_path(path),
        snap_schedule=_schedule(schedule),
        start=_start(start),
        retention_policy=_retention(retention_policy, "retention_policy"),
        subvol=_optional_name(subvolume, "subvolume"),
        group=_optional_name(group_name, "group_name"),
    )
    return client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)


def update(
    client,
    filesystem,
    path,
    retention_to_add=None,
    retention_to_remove=None,
    subvolume=None,
    group_name=None,
    confirm=False,
):
    if retention_to_add is None and retention_to_remove is None:
        raise ConfigurationError("Provide retention_to_add or retention_to_remove.")
    cephfs.boolean(confirm, "confirm")
    if retention_to_remove is not None:
        cephfs.confirmed(confirm, "Removing CephFS snapshot retention")
    data = cephfs.optional_params(
        retention_to_add=_retention(retention_to_add, "retention_to_add"),
        retention_to_remove=_retention(retention_to_remove, "retention_to_remove"),
        subvol=_optional_name(subvolume, "subvolume"),
        group=_optional_name(group_name, "group_name"),
    )
    return client.request("PUT", _route(filesystem, path), api_version=API_VERSION, data=data)


def remove(
    client,
    filesystem,
    path,
    schedule,
    start,
    retention_policy=None,
    subvolume=None,
    group_name=None,
    confirm=False,
):
    cephfs.confirmed(confirm, "Removing a CephFS snapshot schedule")
    params = cephfs.optional_params(
        schedule=_schedule(schedule),
        start=_start(start),
        retention_policy=_retention(retention_policy, "retention_policy"),
        subvol=_optional_name(subvolume, "subvolume"),
        group=_optional_name(group_name, "group_name"),
    )
    return client.request(
        "DELETE",
        f"{_route(filesystem, path)}/delete_snapshot",
        api_version=API_VERSION,
        params=params,
    )


def _activation(client, action, filesystem, path, schedule, start, subvolume, group_name):
    data = cephfs.optional_params(
        schedule=_schedule(schedule),
        start=_start(start),
        subvol=_optional_name(subvolume, "subvolume"),
        group=_optional_name(group_name, "group_name"),
    )
    return client.request(
        "POST",
        f"{_route(filesystem, path)}/{action}",
        api_version=API_VERSION,
        data=data,
    )


def activate(client, filesystem, path, schedule, start, subvolume=None, group_name=None):
    return _activation(client, "activate", filesystem, path, schedule, start, subvolume, group_name)


def deactivate(client, filesystem, path, schedule, start, subvolume=None, group_name=None):
    return _activation(
        client, "deactivate", filesystem, path, schedule, start, subvolume, group_name
    )
