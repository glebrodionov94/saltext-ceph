"""Operations from Dashboard's public ``settings.py`` controller."""

import json
import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/settings"
REDACTED = "***********"
_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,127}")
_SECRET_WORDS = ("PASSWORD", "SECRET", "TOKEN", "KEY")


def normalize_name(value):
    """Return the native upper-case spelling used by Dashboard settings."""
    if not isinstance(value, str) or not _NAME_PATTERN.fullmatch(value):
        raise ConfigurationError("setting name contains unsupported characters.")
    return value.upper().replace("-", "_")


def is_secret(name):
    """Apply Ceph's key/password heuristic plus common secret option names."""
    name = normalize_name(name)
    return any(word in name for word in _SECRET_WORDS)


def _validate_value(value):
    if value is None:
        raise ConfigurationError("setting value must not be None; use delete to reset it.")
    try:
        encoded = json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        raise ConfigurationError("setting value must be JSON-serializable.") from None
    if len(encoded.encode("utf-8")) > 1024 * 1024 or _contains_nul(value):
        raise ConfigurationError("setting value is too large or contains a NUL byte.")
    return value


def _contains_nul(value):
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, Mapping):
        return any(_contains_nul(key) or _contains_nul(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_nul(item) for item in value)
    return False


def normalize_values(values):
    """Validate and canonicalize a non-empty bulk settings mapping."""
    if not isinstance(values, Mapping) or not values:
        raise ConfigurationError("values must be a non-empty mapping.")
    result = {}
    for name, value in values.items():
        native = normalize_name(name)
        if native in result:
            raise ConfigurationError("values contains duplicate setting names.")
        result[native] = _validate_value(value)
    return result


def _redact_nested(value):
    changed = False
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if isinstance(key, str) and any(word in key.upper() for word in _SECRET_WORDS):
                result[key] = REDACTED
                changed = True
            else:
                result[key], item_changed = _redact_nested(item)
                changed = changed or item_changed
        return result, changed
    if isinstance(value, list):
        result = []
        for item in value:
            item, item_changed = _redact_nested(item)
            result.append(item)
            changed = changed or item_changed
        return result, changed
    return value, False


def _safe_setting(item, requested_name=None):
    if not isinstance(item, Mapping):
        raise ProtocolError("Ceph Dashboard setting returned an unexpected response shape.")
    data = dict(item)
    if not {"name", "default", "type", "value"}.issubset(data) or not isinstance(data["type"], str):
        raise ProtocolError("Ceph Dashboard setting returned an unexpected response shape.")
    response_name = data["name"]
    try:
        normalize_name(response_name)
    except ConfigurationError:
        raise ProtocolError(
            "Ceph Dashboard setting returned an unexpected response shape."
        ) from None
    secret = is_secret(requested_name or response_name)
    changed = False
    for field in ("default", "value"):
        if secret:
            data[field] = REDACTED
            changed = True
        else:
            data[field], field_changed = _redact_nested(data[field])
            changed = changed or field_changed
    if changed:
        data["redacted"] = True
    return data


def _names(values):
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError("names must be a non-empty list.")
    result = [normalize_name(value) for value in values]
    if len(set(result)) != len(result):
        raise ConfigurationError("names must not contain duplicates.")
    return result


def list_(client, names=None):
    """List Dashboard settings while redacting credential-like values."""
    names = _names(names)
    params = {"names": ",".join(names)} if names is not None else {}
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION, params=params)
    if not isinstance(response.data, list):
        raise ProtocolError("Ceph Dashboard settings list returned an unexpected response shape.")
    return APIResponse(
        response.status, [_safe_setting(item) for item in response.data], response.headers
    )


def get(client, name):
    """Return one Dashboard setting with secret values redacted."""
    name = normalize_name(name)
    response = client.request(
        "GET", f"{RESOURCE_PATH}/{quote(name, safe='')}", api_version=API_VERSION
    )
    return APIResponse(response.status, _safe_setting(response.data, name), response.headers)


def set_(client, name, value):
    """Set one Dashboard option and discard any echoed value."""
    name = normalize_name(name)
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/{quote(name, safe='')}",
        api_version=API_VERSION,
        data={"value": _validate_value(value)},
    )
    return APIResponse(response.status, {"name": name}, response.headers)


def delete(client, name):
    """Reset one Dashboard option to its default value."""
    name = normalize_name(name)
    response = client.request(
        "DELETE", f"{RESOURCE_PATH}/{quote(name, safe='')}", api_version=API_VERSION
    )
    return APIResponse(response.status, {"name": name}, response.headers)


def bulk_set(client, values):
    """Set multiple Dashboard options and discard all echoed values."""
    values = normalize_values(values)
    response = client.request("PUT", RESOURCE_PATH, api_version=API_VERSION, data=values)
    return APIResponse(response.status, {"names": list(values)}, response.headers)
