"""CephFS subvolume, group and snapshot Dashboard operations."""

from saltext.ceph.utils.ceph import cephfs
from saltext.ceph.utils.ceph.errors import ConfigurationError

API_VERSION = cephfs.API_VERSION
SUBVOLUME_PATH = "/api/cephfs/subvolume"
GROUP_PATH = f"{SUBVOLUME_PATH}/group"
SNAPSHOT_PATH = f"{SUBVOLUME_PATH}/snapshot"


def _group(group_name):
    return None if group_name in (None, "") else cephfs.name(group_name, "group_name")


def subvolume_list(client, volume, group_name=None, info=True):
    volume = cephfs.route_name(volume, "volume")
    params = cephfs.optional_params(
        group_name=_group(group_name), info=cephfs.boolean(info, "info")
    )
    return client.request(
        "GET", f"{SUBVOLUME_PATH}/{volume}", api_version=API_VERSION, params=params
    )


def subvolume_info(client, volume, subvolume, group_name=None):
    volume = cephfs.route_name(volume, "volume")
    params = cephfs.optional_params(
        subvol_name=cephfs.name(subvolume, "subvolume"), group_name=_group(group_name)
    )
    return client.request(
        "GET", f"{SUBVOLUME_PATH}/{volume}/info", api_version=API_VERSION, params=params
    )


def subvolume_create(client, volume, subvolume, options=None):
    data = {
        "vol_name": cephfs.name(volume, "volume"),
        "subvol_name": cephfs.name(subvolume, "subvolume"),
    }
    data.update(cephfs.options(options, reserved=data))
    return client.request("POST", SUBVOLUME_PATH, api_version=API_VERSION, data=data)


def subvolume_resize(client, volume, subvolume, size, group_name=None):
    volume_path = cephfs.route_name(volume, "volume")
    if isinstance(size, bool) or not isinstance(size, (str, int)) or str(size).strip() == "":
        raise ConfigurationError("size must be a non-empty string or integer.")
    data = {
        "subvol_name": cephfs.name(subvolume, "subvolume"),
        "size": size,
    }
    if _group(group_name) is not None:
        data["group_name"] = _group(group_name)
    return client.request(
        "PUT", f"{SUBVOLUME_PATH}/{volume_path}", api_version=API_VERSION, data=data
    )


def subvolume_remove(
    client,
    volume,
    subvolume,
    group_name=None,
    retain_snapshots=False,
    confirm=False,
):
    cephfs.confirmed(confirm, "Removing a CephFS subvolume")
    volume_path = cephfs.route_name(volume, "volume")
    params = cephfs.optional_params(
        subvol_name=cephfs.name(subvolume, "subvolume"),
        group_name=_group(group_name),
        retain_snapshots=cephfs.boolean(retain_snapshots, "retain_snapshots"),
    )
    return client.request(
        "DELETE", f"{SUBVOLUME_PATH}/{volume_path}", api_version=API_VERSION, params=params
    )


def subvolume_exists(client, volume, group_name=None):
    volume_path = cephfs.route_name(volume, "volume")
    return client.request(
        "GET",
        f"{SUBVOLUME_PATH}/{volume_path}/exists",
        api_version=API_VERSION,
        params=cephfs.optional_params(group_name=_group(group_name)),
    )


def snapshot_visibility(client, volume, subvolume, group_name=None):
    """Get snapshot visibility (available in current Ceph, absent in Reef)."""
    volume_path = cephfs.route_name(volume, "volume")
    params = cephfs.optional_params(
        subvol_name=cephfs.name(subvolume, "subvolume"), group_name=_group(group_name)
    )
    return client.request(
        "GET",
        f"{SUBVOLUME_PATH}/{volume_path}/snapshot-visibility",
        api_version=API_VERSION,
        params=params,
    )


def set_snapshot_visibility(client, volume, subvolume, value, group_name=None):
    """Set snapshot visibility (available in current Ceph, absent in Reef)."""
    volume_path = cephfs.route_name(volume, "volume")
    if isinstance(value, bool):
        value = str(value).lower()
    if value not in ("true", "false"):
        raise ConfigurationError("value must be true or false.")
    data = {
        "subvol_name": cephfs.name(subvolume, "subvolume"),
        "value": value,
    }
    if _group(group_name) is not None:
        data["group_name"] = _group(group_name)
    return client.request(
        "PUT",
        f"{SUBVOLUME_PATH}/{volume_path}/snapshot-visibility",
        api_version=API_VERSION,
        data=data,
    )


def group_list(client, volume, info=True):
    volume = cephfs.route_name(volume, "volume")
    return client.request(
        "GET",
        f"{GROUP_PATH}/{volume}",
        api_version=API_VERSION,
        params={"info": cephfs.boolean(info, "info")},
    )


def group_info(client, volume, group_name):
    volume = cephfs.route_name(volume, "volume")
    return client.request(
        "GET",
        f"{GROUP_PATH}/{volume}/info",
        api_version=API_VERSION,
        params={"group_name": cephfs.name(group_name, "group_name")},
    )


def group_create(client, volume, group_name, options=None):
    data = {
        "vol_name": cephfs.name(volume, "volume"),
        "group_name": cephfs.name(group_name, "group_name"),
    }
    data.update(cephfs.options(options, reserved=data))
    return client.request("POST", GROUP_PATH, api_version=API_VERSION, data=data)


def group_resize(client, volume, group_name, size):
    volume_path = cephfs.route_name(volume, "volume")
    if isinstance(size, bool) or not isinstance(size, (str, int)) or str(size).strip() == "":
        raise ConfigurationError("size must be a non-empty string or integer.")
    data = {"group_name": cephfs.name(group_name, "group_name"), "size": size}
    return client.request("PUT", f"{GROUP_PATH}/{volume_path}", api_version=API_VERSION, data=data)


def group_remove(client, volume, group_name, confirm=False):
    cephfs.confirmed(confirm, "Removing a CephFS subvolume group")
    volume_path = cephfs.route_name(volume, "volume")
    return client.request(
        "DELETE",
        f"{GROUP_PATH}/{volume_path}",
        api_version=API_VERSION,
        params={"group_name": cephfs.name(group_name, "group_name")},
    )


def snapshot_list(client, volume, subvolume, group_name=None, info=True):
    volume_path = cephfs.route_name(volume, "volume")
    subvolume_path = cephfs.route_name(subvolume, "subvolume")
    params = cephfs.optional_params(
        group_name=_group(group_name), info=cephfs.boolean(info, "info")
    )
    return client.request(
        "GET",
        f"{SNAPSHOT_PATH}/{volume_path}/{subvolume_path}",
        api_version=API_VERSION,
        params=params,
    )


def snapshot_info(client, volume, subvolume, snapshot, group_name=None):
    volume_path = cephfs.route_name(volume, "volume")
    subvolume_path = cephfs.route_name(subvolume, "subvolume")
    params = cephfs.optional_params(
        snap_name=cephfs.name(snapshot, "snapshot"), group_name=_group(group_name)
    )
    return client.request(
        "GET",
        f"{SNAPSHOT_PATH}/{volume_path}/{subvolume_path}/info",
        api_version=API_VERSION,
        params=params,
    )


def snapshot_create(client, volume, subvolume, snapshot, group_name=None):
    data = {
        "vol_name": cephfs.name(volume, "volume"),
        "subvol_name": cephfs.name(subvolume, "subvolume"),
        "snap_name": cephfs.name(snapshot, "snapshot"),
    }
    if _group(group_name) is not None:
        data["group_name"] = _group(group_name)
    return client.request("POST", SNAPSHOT_PATH, api_version=API_VERSION, data=data)


def snapshot_remove(
    client,
    volume,
    subvolume,
    snapshot,
    group_name=None,
    force=True,
    confirm=False,
):
    cephfs.confirmed(confirm, "Removing a CephFS subvolume snapshot")
    volume_path = cephfs.route_name(volume, "volume")
    subvolume_path = cephfs.route_name(subvolume, "subvolume")
    params = cephfs.optional_params(
        snap_name=cephfs.name(snapshot, "snapshot"),
        group_name=_group(group_name),
        force=cephfs.boolean(force, "force"),
    )
    return client.request(
        "DELETE",
        f"{SNAPSHOT_PATH}/{volume_path}/{subvolume_path}",
        api_version=API_VERSION,
        params=params,
    )


def snapshot_clone(
    client,
    volume,
    subvolume,
    snapshot,
    clone,
    group_name=None,
    target_group_name=None,
):
    data = {
        "vol_name": cephfs.name(volume, "volume"),
        "subvol_name": cephfs.name(subvolume, "subvolume"),
        "snap_name": cephfs.name(snapshot, "snapshot"),
        "clone_name": cephfs.name(clone, "clone"),
    }
    if _group(group_name) is not None:
        data["group_name"] = _group(group_name)
    if _group(target_group_name) is not None:
        data["target_group_name"] = _group(target_group_name)
    return client.request("POST", f"{SNAPSHOT_PATH}/clone", api_version=API_VERSION, data=data)
