"""Operations from Dashboard's public ``erasure_code_profile.py`` controller."""

import math
import re
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/erasure_code_profile"
_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_SETTING_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _name(value):
    if not isinstance(value, str) or not _NAME_PATTERN.fullmatch(value):
        raise ConfigurationError("name contains unsupported characters.")
    return value


def _settings(values):
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise ConfigurationError("settings must be a mapping.")

    normalized = {}
    for key, value in values.items():
        if not isinstance(key, str) or not _SETTING_PATTERN.fullmatch(key):
            raise ConfigurationError("settings contains an invalid key.")
        if key in {"name", "force"}:
            raise ConfigurationError(f"settings must not contain the reserved key {key!r}.")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ConfigurationError(f"settings[{key!r}] must be a string or number.")
        if isinstance(value, str) and not value:
            raise ConfigurationError(f"settings[{key!r}] must not be empty.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ConfigurationError(f"settings[{key!r}] must be finite.")
        normalized[key] = value
    return normalized


validate_profile_name = _name
normalize_settings = _settings


def _profile(response, operation):
    if not isinstance(response.data, Mapping):
        raise ProtocolError(
            f"Ceph erasure-code profile {operation} returned an unexpected response shape."
        )
    return APIResponse(response.status, dict(response.data), response.headers)


def list_(client):
    """Return all erasure-code profiles."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    if not isinstance(response.data, list) or not all(
        isinstance(item, Mapping) for item in response.data
    ):
        raise ProtocolError("Ceph erasure-code profile list returned an unexpected response shape.")
    return APIResponse(response.status, [dict(item) for item in response.data], response.headers)


def get(client, name):
    """Return one erasure-code profile by name."""
    name = quote(_name(name), safe="")
    response = client.request("GET", f"{RESOURCE_PATH}/{name}", api_version=API_VERSION)
    return _profile(response, "get")


def create(client, name, settings=None):
    """Create an erasure-code profile with plugin-specific settings."""
    data = {"name": _name(name)}
    data.update(_settings(settings))
    return client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)


def delete(client, name, confirm=False):
    """Delete one erasure-code profile after explicit confirmation."""
    validation.confirmation(confirm, "Deleting an erasure-code profile")
    name = quote(_name(name), safe="")
    return client.request("DELETE", f"{RESOURCE_PATH}/{name}", api_version=API_VERSION)
