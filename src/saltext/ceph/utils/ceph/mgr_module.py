"""Operations from Dashboard's public ``mgr_modules.py`` controller."""

import math
import re
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import ConfigurationError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/mgr/module"
_OPTION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _module_name(value):
    value = validation.identifier(value, "module_name")
    if value == "selftest":
        raise ConfigurationError("The selftest manager module is not managed by Dashboard.")
    return value


def _path(module_name, suffix=None):
    path = f"{RESOURCE_PATH}/{quote(_module_name(module_name), safe='')}"
    return f"{path}/{suffix}" if suffix else path


def _config(values):
    if not isinstance(values, Mapping):
        raise ConfigurationError("config must be a mapping.")
    normalized = {}
    for key, value in values.items():
        if not isinstance(key, str) or not _OPTION_PATTERN.fullmatch(key):
            raise ConfigurationError("config contains an invalid option name.")
        if value is not None and (
            isinstance(value, (list, dict)) or not isinstance(value, (str, int, float, bool))
        ):
            raise ConfigurationError(f"config[{key!r}] must be a JSON scalar or null.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ConfigurationError(f"config[{key!r}] must be finite.")
        normalized[key] = value
    return normalized


validate_module_name = _module_name
normalize_config = _config


def list_(client):
    """Return manager modules and their enablement metadata."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    return validation.mapping_list_response(response, "Ceph manager module list")


def get_config(client, module_name):
    """Return persistent configuration values for one manager module."""
    response = client.request("GET", _path(module_name), api_version=API_VERSION)
    return validation.mapping_response(response, "Ceph manager module configuration")


def options(client, module_name):
    """Return option definitions for one manager module."""
    response = client.request("GET", _path(module_name, "options"), api_version=API_VERSION)
    return validation.mapping_response(response, "Ceph manager module options")


def set_config(client, module_name, config):
    """Set supplied persistent options for one manager module."""
    return client.request(
        "PUT",
        _path(module_name),
        api_version=API_VERSION,
        data={"config": _config(config)},
    )


def enable(client, module_name, force=False):
    """Enable a manager module, optionally using current Ceph's force flag."""
    if not isinstance(force, bool):
        raise ConfigurationError("force must be a boolean.")
    data = {"force": True} if force else {}
    return client.request("POST", _path(module_name, "enable"), api_version=API_VERSION, data=data)


def disable(client, module_name):
    """Disable a manager module."""
    return client.request("POST", _path(module_name, "disable"), api_version=API_VERSION, data={})
