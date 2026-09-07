"""Shared validation and secret-handling for public RGW adapters."""

import json
import re
from collections.abc import Mapping
from collections.abc import Sequence
from copy import deepcopy
from urllib.parse import quote

from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
REDACTED = "***********"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_PARTS = (
    "secret",
    "password",
    "token",
    "access_key",
    "access-key",
    "private_key",
    "private-key",
    "client_key",
    "client-key",
    "push_endpoint",
    "opaque_data",
)


def boolean(value, label):
    """Require a real boolean; strings are intentionally not coerced."""
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def text(value, label, *, optional=False, max_length=65536):
    """Validate bounded text without control characters."""
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or (not optional and not value)
        or len(value.encode("utf-8")) > max_length
        or _CONTROL.search(value)
    ):
        suffix = " or None" if optional else ""
        raise ConfigurationError(f"{label} must be bounded text{suffix}.")
    return value


def name(value, label="name"):
    """Validate an RGW name that may later be percent-encoded as one segment."""
    return text(value, label, max_length=1024)


def segment(value, label="name"):
    """Return a percent-encoded RGW resource identifier."""
    return quote(name(value, label), safe="")


def optional_text(value, label, *, max_length=65536):
    """Validate optional text while retaining the empty string when supplied."""
    return text(value, label, optional=True, max_length=max_length)


def non_negative(value, label):
    """Normalize a non-negative integer."""
    return validation.non_negative_integer(value, label)


def integer(value, label):
    """Normalize an integer or a signed decimal integer string."""
    if isinstance(value, bool):
        raise ConfigurationError(f"{label} must be an integer.")
    if isinstance(value, str):
        if not re.fullmatch(r"-?[0-9]+", value):
            raise ConfigurationError(f"{label} must be an integer.")
        value = int(value)
    if not isinstance(value, int):
        raise ConfigurationError(f"{label} must be an integer.")
    return value


def positive(value, label):
    """Normalize a positive integer."""
    value = non_negative(value, label)
    if value == 0:
        raise ConfigurationError(f"{label} must be a positive integer.")
    return value


def json_value(value, label):
    """Validate and detach a JSON-compatible value."""
    return validation.json_value(value, label)


def mapping(value, label, *, required=True):
    """Validate and detach a mapping."""
    if value is None and not required:
        return None
    value = json_value(value, label)
    if not isinstance(value, dict) or (required and not value):
        qualifier = "non-empty " if required else ""
        raise ConfigurationError(f"{label} must be a {qualifier}mapping.")
    return value


def mapping_list(value, label, *, optional=False):
    """Validate and detach a list of mappings."""
    if value is None and optional:
        return None
    value = json_value(value, label)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ConfigurationError(f"{label} must be a list of mappings.")
    return value


def string_list(value, label, *, optional=False):
    """Validate a duplicate-free list of bounded RGW names."""
    if value is None and optional:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError(f"{label} must be a list.")
    result = [name(item, label) for item in value]
    if len(result) != len(set(result)):
        raise ConfigurationError(f"{label} must not contain duplicates.")
    return result


def confirm(value):
    """Require an explicit boolean confirmation for a destructive request."""
    boolean(value, "confirm")
    if not value:
        raise ConfigurationError("destructive RGW operation requires confirm=True.")


def secret_from_file(source, label, *, required=False, max_length=65536):
    """Read one secret from an absolute, regular, non-symlink UTF-8 file.

    Salt job arguments are commonly persisted in the job cache.  RGW execution
    modules therefore expose filesystem sources instead of inline credentials.
    Trailing line separators produced by common secret-provisioning tools are
    removed, while embedded control characters remain invalid.
    """
    if source is None:
        if required:
            raise ConfigurationError(f"{label}_source is required.")
        return None
    value = secret_file.read(source).rstrip("\r\n")
    if not value:
        raise ConfigurationError(f"{label} file contains no usable value.")
    return text(value, label, max_length=max_length)


def secret_mapping_from_file(source, label):
    """Read a secret-bearing JSON object through the local file boundary."""
    if source is None:
        raise ConfigurationError(f"{label}_source is required.")
    try:
        value = json.loads(secret_file.read(source))
    except json.JSONDecodeError:
        raise ConfigurationError(f"{label} source must contain JSON.") from None
    return mapping(value, label)


def params(**values):
    """Drop only ``None`` values from a request mapping."""
    return {key: value for key, value in values.items() if value is not None}


def _secret_key(key):
    normalized = key.casefold().replace(" ", "_")
    return any(part in normalized for part in _SECRET_PARTS)


def _redact(value):
    changed = False
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if isinstance(key, str) and _secret_key(key):
                result[key] = REDACTED
                changed = True
            else:
                result[key], item_changed = _redact(item)
                changed = changed or item_changed
        return result, changed
    if isinstance(value, list):
        result = []
        for item in value:
            item, item_changed = _redact(item)
            result.append(item)
            changed = changed or item_changed
        return result, changed
    return deepcopy(value), False


def safe_response(response, label, *, shape="any", include_secrets=False):
    """Validate an RGW response, detach it, and redact credentials by default."""
    boolean(include_secrets, "include_secrets")
    data = response.data
    if shape == "mapping" and not isinstance(data, Mapping):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    if shape == "mapping_or_none" and data is not None and not isinstance(data, Mapping):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    if shape == "mapping_list" and (
        not isinstance(data, list) or not all(isinstance(item, Mapping) for item in data)
    ):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    if shape == "list" and not isinstance(data, list):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    if shape == "boolean" and not isinstance(data, bool):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    try:
        data = validation.json_value(data, label)
    except ConfigurationError:
        raise ProtocolError(f"{label} returned an unexpected response shape.") from None
    changed = False
    if not include_secrets:
        data, changed = _redact(data)
    else:
        data = deepcopy(data)
    if changed and isinstance(data, dict):
        data["redacted"] = True
    return APIResponse(response.status, data, response.headers)


def secret_blob_response(response, label, *, include_secrets=False):
    """Protect a response whose scalar/list values are themselves credentials."""
    boolean(include_secrets, "include_secrets")
    if include_secrets:
        return response_copy(response, label)
    data = response.data
    if not isinstance(data, (list, Mapping)):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    count = len(data)
    return APIResponse(
        response.status,
        {"redacted": True, "count": count, "value": REDACTED},
        response.headers,
    )


def response_copy(response, label):
    """Return a detached, JSON-compatible response without secret filtering."""
    try:
        data = validation.json_value(response.data, label)
    except ConfigurationError:
        raise ProtocolError(f"{label} returned an unexpected response shape.") from None
    return APIResponse(response.status, data, response.headers)
