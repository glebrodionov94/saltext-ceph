"""CephFS volume and namespace operations from Dashboard ``cephfs.py``."""

import math
import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.users import validate_entity

API_VERSION = "1.0"
RESOURCE_PATH = "/api/cephfs"
_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def name(value, label="name"):
    """Validate a Ceph identifier used as one URL path segment."""
    if not isinstance(value, str) or not _NAME_PATTERN.fullmatch(value):
        raise ConfigurationError(f"{label} contains unsupported characters.")
    return value


def identifier(value, label):
    """Validate a non-negative integer identifier and return its string form."""
    if isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a non-negative integer.")
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ConfigurationError(f"{label} must be a non-negative integer.") from None
    if normalized < 0 or str(normalized) != str(value).strip():
        raise ConfigurationError(f"{label} must be a non-negative integer.")
    return str(normalized)


def filesystem_path(value, label="path"):
    """Validate an absolute CephFS path used in a query or JSON document."""
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or re.search(r"[\x00-\x1f\x7f\\]", value)
        or any(part in (".", "..") for part in value.split("/"))
    ):
        raise ConfigurationError(f"{label} must be an unambiguous absolute CephFS path.")
    return value


def route_name(value, label="name"):
    """Encode a validated identifier for use in a URL path."""
    return quote(name(value, label), safe="")


def route_filesystem_path(value):
    """Encode an absolute CephFS path into one Dashboard route segment."""
    return quote(filesystem_path(value), safe="")


def boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def confirmed(value, action):
    """Require an explicit real boolean before a destructive CephFS request."""
    return validation.confirmation(value, action)


def positive_integer(value, label, *, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{label} must be an integer.")
    if value < 0 or (value == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ConfigurationError(f"{label} must be a {qualifier} integer.")
    return value


def text(value, label):
    if not isinstance(value, str) or not value or re.search(r"[\x00-\x1f\x7f]", value):
        raise ConfigurationError(f"{label} must be a non-empty single-line string.")
    return value


def options(value, reserved=()):
    """Validate extra controller arguments while preserving future API fields."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError("options must be a mapping.")
    blocked = set(value).intersection(reserved)
    if blocked:
        raise ConfigurationError("options must not replace explicit arguments.")

    def copy_json(item, depth=0):
        if depth > 8:
            raise ConfigurationError("options are nested too deeply.")
        if isinstance(item, float) and not math.isfinite(item):
            raise ConfigurationError("options must contain finite numbers.")
        if item is None or isinstance(item, (str, int, float, bool)):
            return item
        if isinstance(item, Mapping):
            if not all(isinstance(key, str) and key for key in item):
                raise ConfigurationError("option keys must be non-empty strings.")
            return {key: copy_json(child, depth + 1) for key, child in item.items()}
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            return [copy_json(child, depth + 1) for child in item]
        raise ConfigurationError("options must contain only JSON-compatible values.")

    return copy_json(value)


def optional_params(**values):
    return {key: value for key, value in values.items() if value not in (None, "")}


def list_(client):
    return client.request("GET", RESOURCE_PATH, api_version=API_VERSION)


def create(client, fs_name, service_spec, data_pool=None, metadata_pool=None):
    fs_name = name(fs_name, "fs_name")
    if not isinstance(service_spec, Mapping):
        raise ConfigurationError("service_spec must be a mapping.")
    service_spec = options(service_spec)
    if not isinstance(service_spec.get("placement"), Mapping):
        raise ConfigurationError("service_spec requires a placement mapping.")
    data = {"name": fs_name, "service_spec": service_spec}
    if data_pool is not None:
        data["data_pool"] = name(data_pool, "data_pool")
    if metadata_pool is not None:
        data["metadata_pool"] = name(metadata_pool, "metadata_pool")
    return client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)


def remove(client, fs_name, confirm=False):
    confirmed(confirm, "Removing a CephFS filesystem")
    return client.request(
        "DELETE",
        f"{RESOURCE_PATH}/remove/{route_name(fs_name, 'fs_name')}",
        api_version=API_VERSION,
    )


def rename(client, fs_name, new_name, confirm=False):
    confirmed(confirm, "Renaming a CephFS filesystem")
    data = {"name": name(fs_name, "fs_name"), "new_name": name(new_name, "new_name")}
    return client.request("PUT", f"{RESOURCE_PATH}/rename", api_version=API_VERSION, data=data)


def authorize(client, fs_name, client_id, caps, root_squash=False):
    if isinstance(caps, (str, bytes)) or not isinstance(caps, Sequence) or not caps:
        raise ConfigurationError("caps must be a non-empty list of path/capability strings.")
    caps = [text(item, "caps item") for item in caps]
    if len(caps) % 2:
        raise ConfigurationError("caps must contain path/capability pairs.")
    for cap_path in caps[::2]:
        filesystem_path(cap_path, "caps path")
    data = {
        "fs_name": name(fs_name, "fs_name"),
        "client_id": validate_entity(client_id),
        "caps": caps,
        "root_squash": boolean(root_squash, "root_squash"),
    }
    return client.request("PUT", f"{RESOURCE_PATH}/auth", api_version=API_VERSION, data=data)


def get(client, fs_id):
    fs_id = identifier(fs_id, "fs_id")
    return client.request("GET", f"{RESOURCE_PATH}/{fs_id}", api_version=API_VERSION)


def clients(client, fs_id):
    fs_id = identifier(fs_id, "fs_id")
    return client.request("GET", f"{RESOURCE_PATH}/{fs_id}/clients", api_version=API_VERSION)


def evict_client(client, fs_id, client_id, confirm=False):
    confirmed(confirm, "Evicting a CephFS client")
    fs_id = identifier(fs_id, "fs_id")
    client_id = identifier(client_id, "client_id")
    return client.request(
        "DELETE", f"{RESOURCE_PATH}/{fs_id}/client/{client_id}", api_version=API_VERSION
    )


def mds_counters(client, fs_id, counters=None):
    fs_id = identifier(fs_id, "fs_id")
    if counters is not None:
        if isinstance(counters, (str, bytes)) or not isinstance(counters, Sequence):
            raise ConfigurationError("counters must be a list of counter names.")
        counters = [text(item, "counter") for item in counters]
    return client.request(
        "GET",
        f"{RESOURCE_PATH}/{fs_id}/mds_counters",
        api_version=API_VERSION,
        params=optional_params(counters=counters),
    )


def root_directory(client, fs_id):
    fs_id = identifier(fs_id, "fs_id")
    return client.request(
        "GET", f"{RESOURCE_PATH}/{fs_id}/get_root_directory", api_version=API_VERSION
    )


def list_directories(client, fs_id, path=None, depth=1):
    fs_id = identifier(fs_id, "fs_id")
    if path is not None:
        path = filesystem_path(path)
    depth = positive_integer(depth, "depth", allow_zero=True)
    return client.request(
        "GET",
        f"{RESOURCE_PATH}/{fs_id}/ls_dir",
        api_version=API_VERSION,
        params=optional_params(path=path, depth=depth),
    )


def make_directory(client, fs_id, path):
    fs_id = identifier(fs_id, "fs_id")
    return client.request(
        "POST",
        f"{RESOURCE_PATH}/{fs_id}/tree",
        api_version=API_VERSION,
        data={"path": filesystem_path(path)},
    )


def remove_directory(client, fs_id, path, confirm=False):
    confirmed(confirm, "Removing a CephFS directory")
    fs_id = identifier(fs_id, "fs_id")
    return client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{fs_id}/tree",
        api_version=API_VERSION,
        params={"path": filesystem_path(path)},
    )


def get_quota(client, fs_id, path):
    fs_id = identifier(fs_id, "fs_id")
    return client.request(
        "GET",
        f"{RESOURCE_PATH}/{fs_id}/quota",
        api_version=API_VERSION,
        params={"path": filesystem_path(path)},
    )


def set_quota(client, fs_id, path, max_bytes=None, max_files=None):
    fs_id = identifier(fs_id, "fs_id")
    if max_bytes is None and max_files is None:
        raise ConfigurationError("At least one quota limit must be provided.")
    data = {"path": filesystem_path(path)}
    if max_bytes is not None:
        data["max_bytes"] = positive_integer(max_bytes, "max_bytes", allow_zero=True)
    if max_files is not None:
        data["max_files"] = positive_integer(max_files, "max_files", allow_zero=True)
    return client.request(
        "PUT", f"{RESOURCE_PATH}/{fs_id}/quota", api_version=API_VERSION, data=data
    )


def write_file(client, fs_id, path, contents, confirm=False):
    confirmed(confirm, "Writing or replacing a CephFS file")
    fs_id = identifier(fs_id, "fs_id")
    if not isinstance(contents, str) or "\x00" in contents:
        raise ConfigurationError("contents must be text without NUL bytes.")
    return client.request(
        "POST",
        f"{RESOURCE_PATH}/{fs_id}/write_to_file",
        api_version=API_VERSION,
        data={"path": filesystem_path(path), "buf": contents},
    )


def unlink(client, fs_id, path, confirm=False):
    confirmed(confirm, "Unlinking a CephFS path")
    fs_id = identifier(fs_id, "fs_id")
    return client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{fs_id}/unlink",
        api_version=API_VERSION,
        params={"path": filesystem_path(path)},
    )


def statfs(client, fs_id, path):
    fs_id = identifier(fs_id, "fs_id")
    return client.request(
        "GET",
        f"{RESOURCE_PATH}/{fs_id}/statfs",
        api_version=API_VERSION,
        params={"path": filesystem_path(path)},
    )


def create_snapshot(client, fs_id, path, snapshot_name=None):
    fs_id = identifier(fs_id, "fs_id")
    data = {"path": filesystem_path(path)}
    if snapshot_name is not None:
        data["name"] = name(snapshot_name, "snapshot_name")
    return client.request(
        "POST", f"{RESOURCE_PATH}/{fs_id}/snapshot", api_version=API_VERSION, data=data
    )


def remove_snapshot(client, fs_id, path, snapshot_name, confirm=False):
    confirmed(confirm, "Removing a CephFS directory snapshot")
    fs_id = identifier(fs_id, "fs_id")
    params = {"path": filesystem_path(path), "name": name(snapshot_name, "snapshot_name")}
    return client.request(
        "DELETE", f"{RESOURCE_PATH}/{fs_id}/snapshot", api_version=API_VERSION, params=params
    )


def rename_path(client, fs_id, source, destination, confirm=False):
    confirmed(confirm, "Renaming a CephFS path")
    fs_id = identifier(fs_id, "fs_id")
    data = {
        "src_path": filesystem_path(source, "source"),
        "dst_path": filesystem_path(destination, "destination"),
    }
    return client.request(
        "PUT", f"{RESOURCE_PATH}/{fs_id}/rename-path", api_version=API_VERSION, data=data
    )
