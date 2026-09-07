"""Reusable validation helpers for Ceph Dashboard controller adapters."""

import math
import re
from collections.abc import Mapping
from collections.abc import Sequence

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def identifier(value, label="name", pattern=IDENTIFIER_PATTERN, max_length=255):
    """Validate a bounded identifier intended for one URL path segment."""
    if not isinstance(value, str) or len(value) > max_length or not pattern.fullmatch(value):
        raise ConfigurationError(f"{label} contains unsupported characters.")
    return value


def string_list(
    values,
    label,
    *,
    allowed=None,
    pattern=IDENTIFIER_PATTERN,
    optional=True,
):
    """Validate a non-empty, duplicate-free sequence of bounded identifiers."""
    if values is None and optional:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError(f"{label} must be a non-empty list.")
    normalized = [identifier(value, label, pattern=pattern) for value in values]
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError(f"{label} must not contain duplicates.")
    if allowed is not None and not set(normalized).issubset(allowed):
        raise ConfigurationError(f"{label} contains an unsupported value.")
    return normalized


def mapping_response(response, label):
    """Copy a mapping response into a predictable :class:`APIResponse`."""
    if not isinstance(response.data, Mapping):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    return APIResponse(response.status, dict(response.data), response.headers)


def mapping_list_response(response, label):
    """Copy a list of mappings into a predictable :class:`APIResponse`."""
    if not isinstance(response.data, list) or not all(
        isinstance(item, Mapping) for item in response.data
    ):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    return APIResponse(response.status, [dict(item) for item in response.data], response.headers)


def json_value(value, label="value", max_depth=16):
    """Return a detached JSON-compatible value with finite numbers only."""

    def normalize(item, depth):
        if depth > max_depth:
            raise ConfigurationError(f"{label} exceeds the maximum nesting depth.")
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ConfigurationError(f"{label} must contain only finite numbers.")
            return item
        if isinstance(item, Mapping):
            normalized = {}
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ConfigurationError(f"{label} must use string mapping keys.")
                normalized[key] = normalize(child, depth + 1)
            return normalized
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            return [normalize(child, depth + 1) for child in item]
        raise ConfigurationError(f"{label} must contain only JSON-compatible values.")

    return normalize(value, 0)


def non_negative_integer(value, label="value"):
    """Normalize an integer or decimal string that cannot be negative."""
    if isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a non-negative integer.")
    if isinstance(value, str):
        if not re.fullmatch(r"[0-9]+", value):
            raise ConfigurationError(f"{label} must be a non-negative integer.")
        value = int(value)
    if not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"{label} must be a non-negative integer.")
    return value


def confirmation(value, action="Destructive operation"):
    """Require an explicit real boolean before a destructive API request."""
    if not isinstance(value, bool):
        raise ConfigurationError("confirm must be a boolean.")
    if not value:
        raise ConfigurationError(f"{action} requires confirm=True.")
    return True


def integer_list(values, label="values", *, allow_scalar=False):
    """Normalize a non-empty duplicate-free list of non-negative integers."""
    if allow_scalar and (
        (isinstance(values, int) and not isinstance(values, bool)) or isinstance(values, str)
    ):
        values = [values]
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError(f"{label} must be a non-empty list.")
    normalized = [non_negative_integer(value, label) for value in values]
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError(f"{label} must not contain duplicates.")
    return normalized
