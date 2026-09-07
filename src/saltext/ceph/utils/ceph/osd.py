"""Operations from Dashboard's public ``osd.py`` controllers."""

import json
import re
import uuid
from collections.abc import Mapping
from collections.abc import Sequence

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

RESOURCE_PATH = "/api/osd"
DEFAULT_API_VERSION = "1.0"
LIST_API_VERSION = "1.1"
SETTINGS_API_VERSION = "0.1"
CREATE_METHODS = frozenset(("bare", "drive_groups", "predefined"))
PREDEFINED_OPTIONS = frozenset(("cost_capacity", "throughput_optimized", "iops_optimized"))
MARK_ACTIONS = frozenset(("out", "in", "down", "lost"))
INDIVIDUAL_FLAGS = frozenset(("noin", "noout", "noup", "nodown"))
_SORT_PATTERN = re.compile(r"[+-]?id")
_FLAG_PATTERN = re.compile(r"[a-z][a-z0-9_-]*")
_DEVICE_CLASS_PATTERN = re.compile(r"[A-Za-z0-9_.-]*")


def _osd_id(value):
    """Validate and normalize a non-negative OSD identifier."""
    return validation.non_negative_integer(value, "svc_id")


def _path(svc_id, suffix=None):
    path = f"{RESOURCE_PATH}/{_osd_id(svc_id)}"
    return f"{path}/{suffix}" if suffix else path


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _bounded_text(value, label, *, allow_empty=False, max_length=255):
    if (
        not isinstance(value, str)
        or (not allow_empty and not value)
        or len(value) > max_length
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError(f"{label} must be a bounded text value.")
    return value


def _string_list_response(response, label):
    if not isinstance(response.data, list) or not all(
        isinstance(item, str) for item in response.data
    ):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    return APIResponse(response.status, list(response.data), response.headers)


def _flags(values):
    """Validate and normalize cluster-wide OSD flags."""
    return validation.string_list(values, "flags", pattern=_FLAG_PATTERN, optional=False)


def normalize_individual_flags(flag_values):
    """Validate the supported per-OSD flag mapping."""
    if not isinstance(flag_values, Mapping) or not flag_values:
        raise ConfigurationError("flags must be a non-empty mapping.")
    if not set(flag_values).issubset(INDIVIDUAL_FLAGS):
        raise ConfigurationError("flags contains an unsupported individual OSD flag.")
    normalized = {}
    for name, enabled in flag_values.items():
        if enabled is not None and not isinstance(enabled, bool):
            raise ConfigurationError("individual flag values must be boolean or null.")
        normalized[name] = enabled
    return normalized


normalize_osd_id = _osd_id
normalize_osd_ids = validation.integer_list
normalize_cluster_flags = _flags


def _create_data(method, data):
    data = validation.json_value(data, "data")
    if method == "bare":
        if not isinstance(data, Mapping):
            raise ConfigurationError("data must be a mapping for the bare method.")
        if "svc_id" not in data or "uuid" not in data:
            raise ConfigurationError("bare data requires svc_id and uuid.")
        data = dict(data)
        data["svc_id"] = _osd_id(data["svc_id"])
        try:
            data["uuid"] = str(uuid.UUID(data["uuid"]))
        except (AttributeError, TypeError, ValueError):
            raise ConfigurationError("bare data uuid must be a valid UUID.") from None
        return data

    if (
        isinstance(data, (str, bytes))
        or not isinstance(data, Sequence)
        or not data
        or not all(isinstance(item, Mapping) for item in data)
    ):
        raise ConfigurationError(f"data must be a non-empty list for the {method} method.")
    data = [dict(item) for item in data]
    if method == "predefined":
        if len(data) != 1 or data[0].get("option") not in PREDEFINED_OPTIONS:
            raise ConfigurationError(
                "predefined data requires exactly one supported deployment option."
            )
        if not isinstance(data[0].get("encrypted"), bool):
            raise ConfigurationError("predefined data encrypted must be a boolean.")
    return data


def list_(client, offset=0, limit=-1, search="", sort="+id"):
    """Return all OSDs by default, with optional server-side pagination."""
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ConfigurationError("offset must be a non-negative integer.")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < -1:
        raise ConfigurationError("limit must be -1 or a non-negative integer.")
    search = _bounded_text(search, "search", allow_empty=True)
    if not isinstance(sort, str) or not _SORT_PATTERN.fullmatch(sort):
        raise ConfigurationError("sort must be id, +id, or -id.")
    response = client.request(
        "GET",
        RESOURCE_PATH,
        api_version=LIST_API_VERSION,
        params={"offset": offset, "limit": limit, "search": search, "sort": sort},
    )
    return validation.mapping_list_response(response, "Ceph OSD list")


def get(client, svc_id):
    """Return collected data for one OSD."""
    response = client.request("GET", _path(svc_id), api_version=DEFAULT_API_VERSION)
    return validation.mapping_response(response, "Ceph OSD")


def settings(client):
    """Return cluster near-full and full ratios."""
    response = client.request("GET", f"{RESOURCE_PATH}/settings", api_version=SETTINGS_API_VERSION)
    return validation.mapping_response(response, "Ceph OSD settings")


def smart(client, svc_id):
    """Return SMART data for one OSD's backing devices."""
    response = client.request("GET", _path(svc_id, "smart"), api_version=DEFAULT_API_VERSION)
    return validation.mapping_response(response, "Ceph OSD SMART data")


def histogram(client, svc_id):
    """Return the OSD performance histogram."""
    response = client.request("GET", _path(svc_id, "histogram"), api_version=DEFAULT_API_VERSION)
    return validation.mapping_response(response, "Ceph OSD histogram")


def devices(client, svc_id):
    """Return device-health records associated with one OSD."""
    response = client.request("GET", _path(svc_id, "devices"), api_version=DEFAULT_API_VERSION)
    return validation.mapping_list_response(response, "Ceph OSD device list")


def set_device_class(client, svc_id, device_class):
    """Set the CRUSH device class, or clear it with an empty string."""
    if (
        not isinstance(device_class, str)
        or len(device_class) > 64
        or not _DEVICE_CLASS_PATTERN.fullmatch(device_class)
    ):
        raise ConfigurationError("device_class contains unsupported characters.")
    return client.request(
        "PUT",
        _path(svc_id),
        api_version=DEFAULT_API_VERSION,
        data={"device_class": device_class},
    )


def create(client, method, data, tracking_id, confirm=False):
    """Create bare or orchestrated OSDs after an explicit safety confirmation."""
    if not isinstance(method, str) or method.lower() not in CREATE_METHODS:
        raise ConfigurationError(f"method must be one of: {', '.join(sorted(CREATE_METHODS))}.")
    method = method.lower()
    _boolean(confirm, "confirm")
    if not confirm:
        raise ConfigurationError("Creating OSDs requires confirm=True.")
    tracking_id = _bounded_text(tracking_id, "tracking_id")
    return client.request(
        "POST",
        RESOURCE_PATH,
        api_version=DEFAULT_API_VERSION,
        data={
            "method": method,
            "data": _create_data(method, data),
            "tracking_id": tracking_id,
        },
    )


def remove(client, svc_id, preserve_id=False, force=False, confirm=False):
    """Schedule orchestrated OSD removal with the health check enabled by default."""
    _boolean(preserve_id, "preserve_id")
    _boolean(force, "force")
    _boolean(confirm, "confirm")
    if not confirm:
        raise ConfigurationError("Removing an OSD requires confirm=True.")
    return client.request(
        "DELETE",
        _path(svc_id),
        api_version=DEFAULT_API_VERSION,
        params={"preserve_id": preserve_id, "force": force},
    )


def scrub(client, svc_id, deep=False):
    """Schedule a regular or deep scrub for one OSD."""
    _boolean(deep, "deep")
    return client.request(
        "POST",
        _path(svc_id, "scrub"),
        api_version=DEFAULT_API_VERSION,
        data={"deep": deep},
    )


def mark(client, svc_id, action, confirm=False):
    """Mark one OSD in, out, down, or permanently lost."""
    if not isinstance(action, str) or action.lower() not in MARK_ACTIONS:
        raise ConfigurationError(f"action must be one of: {', '.join(sorted(MARK_ACTIONS))}.")
    action = action.lower()
    _boolean(confirm, "confirm")
    if action == "lost" and not confirm:
        raise ConfigurationError("Marking an OSD lost requires confirm=True.")
    return client.request(
        "PUT",
        _path(svc_id, "mark"),
        api_version=DEFAULT_API_VERSION,
        data={"action": action},
    )


def reweight(client, svc_id, weight):
    """Temporarily set one OSD's weight in the range zero through one."""
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise ConfigurationError("weight must be a number from 0 through 1.")
    weight = float(weight)
    if not 0.0 <= weight <= 1.0:
        raise ConfigurationError("weight must be a number from 0 through 1.")
    return client.request(
        "POST",
        _path(svc_id, "reweight"),
        api_version=DEFAULT_API_VERSION,
        data={"weight": weight},
    )


def purge(client, svc_id, confirm=False):
    """Permanently purge a down OSD."""
    _boolean(confirm, "confirm")
    if not confirm:
        raise ConfigurationError("Purging an OSD requires confirm=True.")
    return client.request("POST", _path(svc_id, "purge"), api_version=DEFAULT_API_VERSION, data={})


def destroy(client, svc_id, confirm=False):
    """Destroy a down OSD while retaining its numeric identifier."""
    _boolean(confirm, "confirm")
    if not confirm:
        raise ConfigurationError("Destroying an OSD requires confirm=True.")
    return client.request(
        "POST", _path(svc_id, "destroy"), api_version=DEFAULT_API_VERSION, data={}
    )


def safe_to_destroy(client, ids):
    """Ask the monitor whether every requested OSD is safe to destroy."""
    ids = validation.integer_list(ids, "ids", allow_scalar=True)
    value = ids[0] if len(ids) == 1 else ids
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/safe_to_destroy",
        api_version=DEFAULT_API_VERSION,
        params={"ids": json.dumps(value, separators=(",", ":"))},
    )
    return validation.mapping_response(response, "Ceph OSD safe-to-destroy check")


def safe_to_delete(client, svc_ids):
    """Ask Dashboard whether cluster health permits OSD removal."""
    ids = validation.integer_list(svc_ids, "svc_ids", allow_scalar=True)
    value = str(ids[0]) if len(ids) == 1 else [str(item) for item in ids]
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/safe_to_delete",
        api_version=DEFAULT_API_VERSION,
        params={"svc_ids": value},
    )
    return validation.mapping_response(response, "Ceph OSD safe-to-delete check")


def flags(client):
    """Return cluster-wide OSD flags."""
    response = client.request("GET", f"{RESOURCE_PATH}/flags", api_version=DEFAULT_API_VERSION)
    return _string_list_response(response, "Ceph OSD flags")


def set_flags(client, flags):  # pylint: disable=redefined-outer-name
    """Replace cluster-wide OSD flags with the supplied complete list."""
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/flags",
        api_version=DEFAULT_API_VERSION,
        data={"flags": _flags(flags)},
    )
    return _string_list_response(response, "Ceph OSD flags")


def individual_flags(client):
    """Return state and individual flags for every OSD."""
    response = client.request(
        "GET", f"{RESOURCE_PATH}/flags/individual", api_version=DEFAULT_API_VERSION
    )
    return validation.mapping_list_response(response, "Ceph individual OSD flags")


def set_individual_flags(client, flags, ids):  # pylint: disable=redefined-outer-name
    """Set or clear supported flags for a selected group of OSDs."""
    normalized_flags = normalize_individual_flags(flags)
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/flags/individual",
        api_version=DEFAULT_API_VERSION,
        data={
            "flags": normalized_flags,
            "ids": validation.integer_list(ids, "ids"),
        },
    )
    return validation.mapping_response(response, "Ceph individual OSD flag update")
