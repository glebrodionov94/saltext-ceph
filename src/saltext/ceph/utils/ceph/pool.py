"""Operations from Dashboard's public ``pool.py`` controller."""

import math
import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import ConfigurationError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/pool"
POOL_TYPES = frozenset(("erasure", "replicated"))
POOL_FLAGS = frozenset(("ec_overwrites",))
_POOL_NAME_PATTERN = re.compile(r"[.A-Za-z0-9_/-]+")
_OPTION_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_APPLICATION_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_RESERVED_OPTIONS = frozenset(
    (
        "application_metadata",
        "configuration",
        "erasure_code_profile",
        "flags",
        "pool",
        "pool_name",
        "pool_type",
        "rbd_mirroring",
        "rule_name",
    )
)


def _pool_name(value, label="pool_name"):
    """Validate and return a pool name."""
    if (
        not isinstance(value, str)
        or len(value) > 255
        or not _POOL_NAME_PATTERN.fullmatch(value)
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ConfigurationError(f"{label} contains unsupported characters.")
    return value


def _resource_path(pool_name, suffix=None):
    path = f"{RESOURCE_PATH}/{quote(_pool_name(pool_name), safe='')}"
    return f"{path}/{suffix}" if suffix else path


def _attrs(values):
    if values is None:
        return None
    if isinstance(values, str):
        values = values.split(",")
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError("attrs must be a non-empty list or comma-separated string.")
    normalized = [
        validation.identifier(value, "attrs", pattern=_OPTION_PATTERN) for value in values
    ]
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError("attrs must not contain duplicates.")
    return ",".join(normalized)


def _boolean(value, label, optional=True):
    if value is None and optional:
        return None
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _name(value, label, optional=True):
    """Validate and return an optional identifier."""
    if value is None and optional:
        return None
    return validation.identifier(value, label)


def _string_list(values, label, *, pattern, allow_empty=False):
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ConfigurationError(f"{label} must be a list of strings.")
    if not values and not allow_empty:
        raise ConfigurationError(f"{label} must be a non-empty list.")
    normalized = [
        validation.identifier(value, label, pattern=pattern, max_length=128) for value in values
    ]
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError(f"{label} must not contain duplicates.")
    return normalized


def _flags(values):
    """Validate and normalize pool flags."""
    normalized = _string_list(values, "flags", pattern=validation.IDENTIFIER_PATTERN)
    if normalized is not None and not set(normalized).issubset(POOL_FLAGS):
        raise ConfigurationError("flags contains an unsupported value.")
    return normalized


def _applications(values):
    """Validate and normalize pool application metadata names."""
    return _string_list(
        values,
        "application_metadata",
        pattern=_APPLICATION_PATTERN,
        allow_empty=True,
    )


def _scalar(value, label, *, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ConfigurationError(f"{label} must be finite.")
        return value
    if isinstance(value, str):
        if len(value) > 4096 or re.search(r"[\x00-\x1f\x7f]", value):
            raise ConfigurationError(f"{label} must be a bounded scalar value.")
        return value
    suffix = " or null" if allow_none else ""
    raise ConfigurationError(f"{label} must be a JSON scalar{suffix}.")


def _options(values, *, reserved=()):
    """Validate and normalize mutable pool options."""
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise ConfigurationError("options must be a mapping.")
    normalized = {}
    blocked = _RESERVED_OPTIONS | frozenset(reserved)
    for key, value in values.items():
        if not isinstance(key, str) or not _OPTION_PATTERN.fullmatch(key):
            raise ConfigurationError("options contains an invalid key.")
        if key in blocked:
            raise ConfigurationError(f"options must not contain the reserved key {key!r}.")
        normalized[key] = _scalar(value, f"options[{key!r}]")
    return normalized


def _configuration(values):
    """Validate and normalize per-pool RBD configuration."""
    if values is None:
        return None
    if not isinstance(values, Mapping):
        raise ConfigurationError("configuration must be a mapping.")
    normalized = {}
    for key, value in values.items():
        if not isinstance(key, str) or not _OPTION_PATTERN.fullmatch(key):
            raise ConfigurationError("configuration contains an invalid option name.")
        normalized[key] = _scalar(value, f"configuration[{key!r}]", allow_none=True)
    return normalized


validate_pool_name = _pool_name
normalize_flags = _flags
normalize_applications = _applications
normalize_configuration = _configuration
normalize_options = _options
normalize_optional_name = _name


def list_(client, attrs=None, stats=False):
    """Return pools, optionally selecting attributes and runtime statistics."""
    attrs = _attrs(attrs)
    stats = _boolean(stats, "stats", optional=False)
    params = {"stats": stats}
    if attrs is not None:
        params["attrs"] = attrs
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION, params=params)
    return validation.mapping_list_response(response, "Ceph pool list")


def get(client, pool_name, attrs=None, stats=False):
    """Return one pool and its RBD configuration."""
    attrs = _attrs(attrs)
    stats = _boolean(stats, "stats", optional=False)
    params = {"stats": stats}
    if attrs is not None:
        params["attrs"] = attrs
    response = client.request(
        "GET", _resource_path(pool_name), api_version=API_VERSION, params=params
    )
    return validation.mapping_response(response, "Ceph pool")


def configuration(client, pool_name):
    """Return RBD configuration entries stored on one pool."""
    response = client.request(
        "GET",
        _resource_path(pool_name, "configuration"),
        api_version=API_VERSION,
    )
    return validation.mapping_list_response(response, "Ceph pool configuration")


def create(
    client,
    pool,
    pg_num,
    pool_type,
    erasure_code_profile=None,
    flags=None,
    application_metadata=None,
    rule_name=None,
    rbd_configuration=None,
    rbd_mirroring=None,
    options=None,
):
    """Create a pool and apply optional pool and RBD configuration values."""
    pool = _pool_name(pool, "pool")
    if isinstance(pg_num, bool) or not isinstance(pg_num, int) or pg_num <= 0:
        raise ConfigurationError("pg_num must be a positive integer.")
    if not isinstance(pool_type, str) or pool_type.lower() not in POOL_TYPES:
        raise ConfigurationError(f"pool_type must be one of: {', '.join(sorted(POOL_TYPES))}.")
    pool_type = pool_type.lower()
    erasure_code_profile = _name(erasure_code_profile, "erasure_code_profile")
    if pool_type == "replicated" and erasure_code_profile is not None:
        raise ConfigurationError("erasure_code_profile is only valid for an erasure pool.")
    flags = _flags(flags)
    if flags and pool_type != "erasure":
        raise ConfigurationError("ec_overwrites is only valid for an erasure pool.")
    application_metadata = _applications(application_metadata)
    rule_name = _name(rule_name, "rule_name")
    rbd_configuration = _configuration(rbd_configuration)
    rbd_mirroring = _boolean(rbd_mirroring, "rbd_mirroring")

    data = {"pool": pool, "pg_num": pg_num, "pool_type": pool_type}
    data.update(_options(options, reserved=("pg_num",)))
    for key, value in {
        "erasure_code_profile": erasure_code_profile,
        "flags": flags,
        "application_metadata": application_metadata,
        "rule_name": rule_name,
        "configuration": rbd_configuration,
        "rbd_mirroring": rbd_mirroring,
    }.items():
        if value is not None:
            data[key] = value
    return client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)


def update(
    client,
    pool_name,
    new_name=None,
    flags=None,
    application_metadata=None,
    rbd_configuration=None,
    rbd_mirroring=None,
    options=None,
):
    """Update mutable pool values and optionally rename the pool."""
    pool_name = _pool_name(pool_name)
    if new_name is not None:
        new_name = _pool_name(new_name, "new_name")
        if new_name == pool_name:
            raise ConfigurationError("new_name must differ from pool_name.")
    flags = _flags(flags)
    application_metadata = _applications(application_metadata)
    rbd_configuration = _configuration(rbd_configuration)
    rbd_mirroring = _boolean(rbd_mirroring, "rbd_mirroring")
    data = _options(options)
    for key, value in {
        "pool": new_name,
        "flags": flags,
        "application_metadata": application_metadata,
        "configuration": rbd_configuration,
        "rbd_mirroring": rbd_mirroring,
    }.items():
        if value is not None:
            data[key] = value
    if not data:
        raise ConfigurationError("At least one pool update value must be provided.")
    return client.request("PUT", _resource_path(pool_name), api_version=API_VERSION, data=data)


def delete(client, pool_name, confirm=False):
    """Permanently delete a pool after explicit local confirmation."""
    validation.confirmation(confirm, "Deleting a RADOS pool")
    return client.request("DELETE", _resource_path(pool_name), api_version=API_VERSION)
