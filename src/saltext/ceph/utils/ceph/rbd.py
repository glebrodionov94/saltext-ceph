"""RBD image operations from Dashboard's public ``rbd.py`` controller."""

import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
LIST_API_VERSION = "2.0"
IMAGE_PATH = "/api/block/image"
TRASH_PATH = f"{IMAGE_PATH}/trash"
POOL_PATH = "/api/block/pool"
FEATURES = frozenset(
    (
        "data-pool",
        "deep-flatten",
        "exclusive-lock",
        "fast-diff",
        "journaling",
        "layering",
        "object-map",
        "operations",
        "striping",
    )
)
MIRROR_MODES = frozenset(("journal", "snapshot"))
SCHEDULE_LEVELS = frozenset(("cluster", "image", "pool"))
_CONFIGURATION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_SORT = re.compile(r"[+-](name|namespace|pool_name)")
_SCHEDULE = re.compile(r"[1-9][0-9]*[mhd]")


def _name(value, label):
    return validation.identifier(value, label)


def _optional_name(value, label):
    return None if value is None else _name(value, label)


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _integer(value, label, *, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{label} must be an integer.")
    if value < 0 or (value == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ConfigurationError(f"{label} must be a {qualifier} integer.")
    return value


def _confirmed(value, action):
    _boolean(value, "confirm")
    if not value:
        raise ConfigurationError(f"{action} requires confirm=True.")


def _text(value, label, *, optional=False, allow_empty=False, max_length=1024):
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or len(value) > max_length
        or (not value and not allow_empty)
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError(f"{label} must be bounded single-line text.")
    return value


def _features(values, *, allow_empty=False):
    if values is None:
        return None
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",") if item.strip()]
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ConfigurationError("features must be a list or comma-separated string.")
    if not values and not allow_empty:
        raise ConfigurationError("features must be non-empty.")
    normalized = [_name(value, "features") for value in values]
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError("features must not contain duplicates.")
    if not set(normalized).issubset(FEATURES):
        raise ConfigurationError("features contains an unsupported RBD feature.")
    return normalized


def _mapping(values, label, *, key_pattern=None, string_values=False):
    if values is None:
        return None
    if not isinstance(values, Mapping) or not values:
        raise ConfigurationError(f"{label} must be a non-empty mapping.")
    result = validation.json_value(values, label)
    for key, value in result.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 255
            or re.search(r"[\x00-\x1f\x7f]", key)
            or (key_pattern is not None and not key_pattern.fullmatch(key))
        ):
            raise ConfigurationError(f"{label} contains an invalid key.")
        if string_values:
            if value is not None and not isinstance(value, str):
                raise ConfigurationError(f"{label} values must be strings or null.")
        elif value is not None and not isinstance(value, (str, bool, int, float)):
            raise ConfigurationError(f"{label} values must be JSON scalars or null.")
    return result


def _layout(obj_size=None, stripe_unit=None, stripe_count=None, data_pool=None):
    result = {}
    if obj_size is not None:
        obj_size = _integer(obj_size, "obj_size")
        if obj_size & (obj_size - 1):
            raise ConfigurationError("obj_size must be a power of two.")
        result["obj_size"] = obj_size
    if stripe_unit is not None:
        result["stripe_unit"] = _integer(stripe_unit, "stripe_unit")
    if stripe_count is not None:
        result["stripe_count"] = _integer(stripe_count, "stripe_count")
    if data_pool is not None:
        result["data_pool"] = _name(data_pool, "data_pool")
    return result


def _schedule_interval(value):
    if value is None:
        return None
    if not isinstance(value, str) or not _SCHEDULE.fullmatch(value):
        raise ConfigurationError("schedule_interval must use a positive m, h, or d interval.")
    return value


def _mirror_mode(value, label="mirror_mode"):
    if value is None:
        return None
    if not isinstance(value, str) or value not in MIRROR_MODES:
        raise ConfigurationError(f"{label} must be one of: {', '.join(sorted(MIRROR_MODES))}.")
    return value


def validate_image_spec(value, label="image_spec"):
    """Validate an unencoded ``pool[/namespace]/image`` specification."""
    if not isinstance(value, str) or value.count("/") not in (1, 2):
        raise ConfigurationError(f"{label} must be pool/image or pool/namespace/image.")
    parts = value.split("/")
    for index, part in enumerate(parts):
        part_label = (
            ("pool_name", "image_name")
            if len(parts) == 2
            else (
                "pool_name",
                "namespace",
                "image_name",
            )
        )
        _name(part, part_label[index])
    return value


def make_image_spec(pool_name, image_name, namespace=None):
    """Build a validated, unencoded image specification."""
    parts = [_name(pool_name, "pool_name")]
    if namespace is not None:
        parts.append(_name(namespace, "namespace"))
    parts.append(_name(image_name, "image_name"))
    return "/".join(parts)


def _spec_path(value, suffix=None, label="image_spec"):
    path = f"{IMAGE_PATH}/{quote(validate_image_spec(value, label), safe='')}"
    return f"{path}/{suffix}" if suffix else path


def _snapshot_path(value, snapshot_name, suffix=None):
    path = f"{_spec_path(value)}/snap/{quote(_name(snapshot_name, 'snapshot_name'), safe='')}"
    return f"{path}/{suffix}" if suffix else path


def _copy_mapping_response(response, label):
    return validation.mapping_response(response, label)


def _copy_mapping_list_response(response, label):
    return validation.mapping_list_response(response, label)


def list_(client, pool_name=None, namespace=None, offset=0, limit=5, search="", sort=""):
    """List images with Dashboard's v2.0 pagination contract."""
    offset = _integer(offset, "offset", allow_zero=True)
    if limit != -1:
        limit = _integer(limit, "limit")
    search = _text(search, "search", allow_empty=True)
    sort = _text(sort, "sort", allow_empty=True, max_length=64)
    if sort and not _SORT.fullmatch(sort):
        raise ConfigurationError("sort must be +name, -name, +pool_name, or a namespace variant.")
    params = {"offset": offset, "limit": limit, "search": search, "sort": sort}
    if pool_name is not None:
        params["pool_name"] = _name(pool_name, "pool_name")
    if namespace is not None:
        params["namespace"] = _name(namespace, "namespace")
    response = client.request("GET", IMAGE_PATH, api_version=LIST_API_VERSION, params=params)
    response = _copy_mapping_list_response(response, "Ceph RBD image list")
    result = []
    for item in response.data:
        values = item.get("value")
        if not isinstance(item.get("pool_name"), str) or not isinstance(values, list):
            raise ProtocolError("Ceph RBD image list returned an invalid pool group.")
        if not all(isinstance(image, Mapping) for image in values):
            raise ProtocolError("Ceph RBD image list returned an invalid image entry.")
        normalized = dict(item)
        normalized["value"] = [dict(image) for image in values]
        result.append(normalized)
    return APIResponse(response.status, result, response.headers)


def get(client, image_spec, omit_usage=False):
    """Return one image; ``omit_usage`` is supported by current Ceph main."""
    _boolean(omit_usage, "omit_usage")
    kwargs = {"params": {"omit_usage": True}} if omit_usage else {}
    response = client.request("GET", _spec_path(image_spec), api_version=API_VERSION, **kwargs)
    return _copy_mapping_response(response, "Ceph RBD image")


def create(
    client,
    name,
    pool_name,
    size,
    namespace=None,
    schedule_interval=None,
    obj_size=None,
    features=None,
    stripe_unit=None,
    stripe_count=None,
    data_pool=None,
    configuration=None,
    metadata=None,
    mirror_mode=None,
):
    """Create an image and optionally enable snapshot or journal mirroring."""
    data = {
        "name": _name(name, "name"),
        "pool_name": _name(pool_name, "pool_name"),
        "size": _integer(size, "size"),
    }
    if namespace is not None:
        data["namespace"] = _name(namespace, "namespace")
    data.update(_layout(obj_size, stripe_unit, stripe_count, data_pool))
    features = _features(features)
    configuration = _mapping(configuration, "configuration", key_pattern=_CONFIGURATION_NAME)
    metadata = _mapping(metadata, "metadata", string_values=True)
    mirror_mode = _mirror_mode(mirror_mode)
    schedule_interval = _schedule_interval(schedule_interval)
    if schedule_interval is not None and mirror_mode != "snapshot":
        raise ConfigurationError("schedule_interval requires mirror_mode='snapshot'.")
    for key, value in {
        "features": features,
        "configuration": configuration,
        "metadata": metadata,
        "mirror_mode": mirror_mode,
        "schedule_interval": schedule_interval,
    }.items():
        if value is not None:
            data[key] = value
    return client.request("POST", IMAGE_PATH, api_version=API_VERSION, data=data)


def update(
    client,
    image_spec,
    name=None,
    size=None,
    features=None,
    configuration=None,
    metadata=None,
    enable_mirror=None,
    primary=None,
    force=False,
    resync=False,
    mirror_mode=None,
    image_mirror_mode=None,
    schedule_interval=None,
    remove_scheduling=False,
    schedule_level=None,
    confirm=False,
):
    """Update image properties and current/main mirroring actions."""
    validate_image_spec(image_spec)
    _boolean(force, "force")
    _boolean(resync, "resync")
    _boolean(remove_scheduling, "remove_scheduling")
    _boolean(confirm, "confirm")
    if enable_mirror is not None:
        _boolean(enable_mirror, "enable_mirror")
    if primary is not None:
        _boolean(primary, "primary")
    if force and primary is not True:
        raise ConfigurationError("force is only valid when promoting an image.")
    if size is not None or enable_mirror is False or primary is not None or force or resync:
        _confirmed(confirm, "Resizing or changing image primary/mirroring state")
    if remove_scheduling:
        _confirmed(confirm, "Removing an RBD snapshot schedule")

    data = {}
    if name is not None:
        data["name"] = _name(name, "name")
    if size is not None:
        data["size"] = _integer(size, "size")
    if features is not None:
        data["features"] = _features(features, allow_empty=True)
    if configuration is not None:
        data["configuration"] = _mapping(
            configuration, "configuration", key_pattern=_CONFIGURATION_NAME
        )
    if metadata is not None:
        data["metadata"] = _mapping(metadata, "metadata", string_values=True)
    if enable_mirror is not None:
        data["enable_mirror"] = enable_mirror
    if primary is not None:
        data["primary"] = primary
    if force:
        data["force"] = True
    if resync:
        data["resync"] = True
    mirror_mode = _mirror_mode(mirror_mode)
    image_mirror_mode = _mirror_mode(image_mirror_mode, "image_mirror_mode")
    if enable_mirror is True and mirror_mode is None:
        raise ConfigurationError("Enabling image mirroring requires mirror_mode.")
    if image_mirror_mode is not None and mirror_mode is None:
        raise ConfigurationError("image_mirror_mode requires mirror_mode.")
    if image_mirror_mode is not None and image_mirror_mode != mirror_mode:
        _confirmed(confirm, "Changing an RBD image mirroring mode")
    if mirror_mode is not None:
        data["mirror_mode"] = mirror_mode
    if image_mirror_mode is not None:
        data["image_mirror_mode"] = image_mirror_mode
    schedule_interval = _schedule_interval(schedule_interval)
    if schedule_interval is not None:
        data["schedule_interval"] = schedule_interval
    if remove_scheduling:
        data["remove_scheduling"] = True
    if schedule_level is not None:
        if schedule_level not in SCHEDULE_LEVELS:
            raise ConfigurationError(
                f"schedule_level must be one of: {', '.join(sorted(SCHEDULE_LEVELS))}."
            )
        if schedule_interval is None and not remove_scheduling:
            raise ConfigurationError("schedule_level requires a schedule change.")
        data["schedule_level"] = schedule_level
    if not data:
        raise ConfigurationError("At least one image update value must be provided.")
    return client.request("PUT", _spec_path(image_spec), api_version=API_VERSION, data=data)


def delete(client, image_spec, confirm=False):
    """Permanently delete an image and its snapshots after confirmation."""
    _confirmed(confirm, "Deleting an RBD image")
    return client.request("DELETE", _spec_path(image_spec), api_version=API_VERSION)


def copy(
    client,
    image_spec,
    dest_pool_name,
    dest_namespace,
    dest_image_name,
    snapshot_name=None,
    obj_size=None,
    features=None,
    stripe_unit=None,
    stripe_count=None,
    data_pool=None,
    configuration=None,
    metadata=None,
):
    """Copy an image or one snapshot into a new image."""
    data = {
        "dest_pool_name": _name(dest_pool_name, "dest_pool_name"),
        "dest_namespace": (
            "" if dest_namespace in (None, "") else _name(dest_namespace, "dest_namespace")
        ),
        "dest_image_name": _name(dest_image_name, "dest_image_name"),
    }
    data.update(_layout(obj_size, stripe_unit, stripe_count, data_pool))
    for key, value in {
        "snapshot_name": _optional_name(snapshot_name, "snapshot_name"),
        "features": _features(features),
        "configuration": _mapping(configuration, "configuration", key_pattern=_CONFIGURATION_NAME),
        "metadata": _mapping(metadata, "metadata", string_values=True),
    }.items():
        if value is not None:
            data[key] = value
    return client.request(
        "POST", _spec_path(image_spec, "copy"), api_version=API_VERSION, data=data
    )


def flatten(client, image_spec, confirm=False):
    """Remove a clone's dependency on its parent after confirmation."""
    _confirmed(confirm, "Flattening an RBD image")
    return client.request(
        "POST", _spec_path(image_spec, "flatten"), api_version=API_VERSION, data={}
    )


def default_features(client):
    """Return the cluster's default RBD feature names."""
    response = client.request("GET", f"{IMAGE_PATH}/default_features", api_version=API_VERSION)
    if not isinstance(response.data, list) or not all(
        isinstance(item, str) for item in response.data
    ):
        raise ProtocolError("Ceph RBD default features returned an unexpected response shape.")
    return APIResponse(response.status, list(response.data), response.headers)


def clone_format_version(client):
    """Return the configured clone format version."""
    response = client.request("GET", f"{IMAGE_PATH}/clone_format_version", api_version=API_VERSION)
    if isinstance(response.data, bool) or not isinstance(response.data, int):
        raise ProtocolError("Ceph RBD clone format returned an unexpected response shape.")
    return response


def move_to_trash(client, image_spec, delay=0, confirm=False):
    """Move an image to trash with an optional deferment period in seconds."""
    _confirmed(confirm, "Moving an RBD image to trash")
    delay = _integer(delay, "delay", allow_zero=True)
    return client.request(
        "POST",
        _spec_path(image_spec, "move_trash"),
        api_version=API_VERSION,
        data={"delay": delay},
    )


def trash_list(client, pool_name=None):
    """List trash entries, optionally for one pool."""
    kwargs = {}
    if pool_name is not None:
        kwargs["params"] = {"pool_name": _name(pool_name, "pool_name")}
    response = client.request("GET", TRASH_PATH, api_version=API_VERSION, **kwargs)
    return _copy_mapping_list_response(response, "Ceph RBD trash list")


def trash_purge(client, pool_name=None, confirm=False):
    """Permanently remove expired trash entries after confirmation."""
    _confirmed(confirm, "Purging RBD trash")
    kwargs = {"data": {}}
    if pool_name is not None:
        kwargs["params"] = {"pool_name": _name(pool_name, "pool_name")}
    return client.request("POST", f"{TRASH_PATH}/purge", api_version=API_VERSION, **kwargs)


def trash_restore(client, image_id_spec, new_image_name):
    """Restore one trash entry under a new image name."""
    return client.request(
        "POST",
        _spec_path(image_id_spec, "restore", label="image_id_spec").replace(
            IMAGE_PATH, TRASH_PATH, 1
        ),
        api_version=API_VERSION,
        data={"new_image_name": _name(new_image_name, "new_image_name")},
    )


def trash_delete(client, image_id_spec, force=False, confirm=False):
    """Permanently remove one trash entry after confirmation."""
    _confirmed(confirm, "Deleting an RBD trash entry")
    _boolean(force, "force")
    path = _spec_path(image_id_spec, label="image_id_spec").replace(IMAGE_PATH, TRASH_PATH, 1)
    return client.request("DELETE", path, api_version=API_VERSION, params={"force": force})


def namespace_list(client, pool_name):
    """List namespaces and image counts for one pool."""
    path = f"{POOL_PATH}/{quote(_name(pool_name, 'pool_name'), safe='')}/namespace"
    response = client.request("GET", path, api_version=API_VERSION)
    return _copy_mapping_list_response(response, "Ceph RBD namespace list")


def namespace_create(client, pool_name, namespace):
    """Create a namespace in one RBD pool."""
    path = f"{POOL_PATH}/{quote(_name(pool_name, 'pool_name'), safe='')}/namespace"
    return client.request(
        "POST",
        path,
        api_version=API_VERSION,
        data={"namespace": _name(namespace, "namespace")},
    )


def namespace_delete(client, pool_name, namespace, confirm=False):
    """Delete an empty namespace after confirmation."""
    _confirmed(confirm, "Deleting an RBD namespace")
    pool_name = quote(_name(pool_name, "pool_name"), safe="")
    namespace = quote(_name(namespace, "namespace"), safe="")
    return client.request(
        "DELETE",
        f"{POOL_PATH}/{pool_name}/namespace/{namespace}",
        api_version=API_VERSION,
    )


def snapshot_create(client, image_spec, snapshot_name, mirror_image_snapshot=False):
    """Create a regular snapshot or a manual mirror snapshot."""
    _boolean(mirror_image_snapshot, "mirror_image_snapshot")
    return client.request(
        "POST",
        f"{_spec_path(image_spec)}/snap",
        api_version=API_VERSION,
        data={
            "snapshot_name": _name(snapshot_name, "snapshot_name"),
            "mirrorImageSnapshot": mirror_image_snapshot,
        },
    )


def snapshot_update(client, image_spec, snapshot_name, new_snapshot_name=None, is_protected=None):
    """Rename, protect, or unprotect an image snapshot."""
    data = {}
    if new_snapshot_name is not None:
        new_snapshot_name = _name(new_snapshot_name, "new_snapshot_name")
        if new_snapshot_name == snapshot_name:
            raise ConfigurationError("new_snapshot_name must differ from snapshot_name.")
        data["new_snap_name"] = new_snapshot_name
    if is_protected is not None:
        data["is_protected"] = _boolean(is_protected, "is_protected")
    if not data:
        raise ConfigurationError("At least one snapshot update value must be provided.")
    return client.request(
        "PUT",
        _snapshot_path(image_spec, snapshot_name),
        api_version=API_VERSION,
        data=data,
    )


def snapshot_delete(client, image_spec, snapshot_name, confirm=False):
    """Permanently delete an image snapshot after confirmation."""
    _confirmed(confirm, "Deleting an RBD snapshot")
    return client.request(
        "DELETE", _snapshot_path(image_spec, snapshot_name), api_version=API_VERSION
    )


def snapshot_rollback(client, image_spec, snapshot_name, confirm=False):
    """Replace current image contents with a snapshot after confirmation."""
    _confirmed(confirm, "Rolling back an RBD snapshot")
    return client.request(
        "POST",
        _snapshot_path(image_spec, snapshot_name, "rollback"),
        api_version=API_VERSION,
        data={},
    )


def snapshot_clone(
    client,
    image_spec,
    snapshot_name,
    child_pool_name,
    child_image_name,
    child_namespace=None,
    obj_size=None,
    features=None,
    stripe_unit=None,
    stripe_count=None,
    data_pool=None,
    configuration=None,
    metadata=None,
    clone_by_snap_id=False,
):
    """Clone an image snapshot; ID-based clone lookup is current-main only."""
    _boolean(clone_by_snap_id, "clone_by_snap_id")
    if clone_by_snap_id and not (
        isinstance(snapshot_name, str) and snapshot_name.isascii() and snapshot_name.isdecimal()
    ):
        raise ConfigurationError("snapshot_name must be a decimal ID with clone_by_snap_id=True.")
    data = {
        "child_pool_name": _name(child_pool_name, "child_pool_name"),
        "child_image_name": _name(child_image_name, "child_image_name"),
    }
    if child_namespace is not None:
        data["child_namespace"] = _name(child_namespace, "child_namespace")
    data.update(_layout(obj_size, stripe_unit, stripe_count, data_pool))
    for key, value in {
        "features": _features(features),
        "configuration": _mapping(configuration, "configuration", key_pattern=_CONFIGURATION_NAME),
        "metadata": _mapping(metadata, "metadata", string_values=True),
    }.items():
        if value is not None:
            data[key] = value
    if clone_by_snap_id:
        data["clone_by_snap_id"] = True
    return client.request(
        "POST",
        _snapshot_path(image_spec, snapshot_name, "clone"),
        api_version=API_VERSION,
        data=data,
    )
