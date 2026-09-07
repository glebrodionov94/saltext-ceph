"""Operations from Dashboard's ``cluster_configuration.py`` controller."""

import math
import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/cluster_conf"
_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]*")
_SECTION_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.-]*"
    r"(?:(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?:[A-Za-z0-9][A-Za-z0-9_.-]*)?"
)


def validate_name(name):
    """Validate a monitor or ``mgr/cephadm`` configuration option name."""
    if not isinstance(name, str) or not _NAME_PATTERN.fullmatch(name):
        raise ConfigurationError("name contains unsupported configuration-option characters.")
    return name


def validate_section(section):
    """Validate a Ceph configuration section such as ``global`` or ``osd.1``."""
    if not isinstance(section, str) or not _SECTION_PATTERN.fullmatch(section):
        raise ConfigurationError("section contains unsupported characters.")
    return section


def _value(value, *, allow_none):
    if value is None:
        if allow_none:
            return None
        raise ConfigurationError("A bulk configuration value cannot be null.")
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes)):
        raise ConfigurationError("Configuration values must be scalar values.")
    if isinstance(value, bytes) or not isinstance(value, (str, bool, int, float)):
        raise ConfigurationError("Configuration values must be strings, booleans, or numbers.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigurationError("Configuration values must be finite.")
    if isinstance(value, str) and re.search(r"[\x00-\x1f\x7f]", value):
        raise ConfigurationError("Configuration values must be single-line strings.")
    return value


def validate_values(values):
    """Validate the controller's list of section/value assignments."""
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError("values must be a non-empty list of section/value mappings.")
    normalized = []
    sections = set()
    for entry in values:
        if not isinstance(entry, Mapping) or set(entry) != {"section", "value"}:
            raise ConfigurationError("Each value requires only section and value fields.")
        section = validate_section(entry["section"])
        if section in sections:
            raise ConfigurationError("values must not contain duplicate sections.")
        sections.add(section)
        normalized.append({"section": section, "value": _value(entry["value"], allow_none=True)})
    return normalized


def validate_options(options):
    """Validate the controller's bulk ``{name: {section, value}}`` mapping."""
    if not isinstance(options, Mapping) or not options:
        raise ConfigurationError("options must be a non-empty mapping.")
    normalized = {}
    for name, entry in options.items():
        name = validate_name(name)
        if not isinstance(entry, Mapping) or set(entry) != {"section", "value"}:
            raise ConfigurationError("Each bulk option requires only section and value fields.")
        normalized[name] = {
            "section": validate_section(entry["section"]),
            "value": _value(entry["value"], allow_none=False),
        }
    return normalized


def _option_list(response, operation):
    if not isinstance(response.data, list) or not all(
        isinstance(item, Mapping) for item in response.data
    ):
        raise ProtocolError(f"Ceph configuration {operation} returned an unexpected response.")
    return APIResponse(response.status, [dict(item) for item in response.data], response.headers)


def list_(client):
    """Return every configuration option and its explicit section values."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    return _option_list(response, "list")


def get(client, name):
    """Return metadata and explicit values for one configuration option."""
    name = quote(validate_name(name), safe="")
    response = client.request("GET", f"{RESOURCE_PATH}/{name}", api_version=API_VERSION)
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph configuration get returned an unexpected response.")
    return APIResponse(response.status, dict(response.data), response.headers)


def filter_(client, names):
    """Return all known options from a non-empty list of names."""
    if isinstance(names, (str, bytes)) or not isinstance(names, Sequence) or not names:
        raise ConfigurationError("names must be a non-empty list of option names.")
    normalized = [validate_name(name) for name in names]
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError("names must not contain duplicates.")
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/filter",
        api_version=API_VERSION,
        params={"names": ",".join(normalized)},
    )
    return _option_list(response, "filter")


def set_(client, name, values, force_update=None):
    """Set or remove explicit section values for one option.

    Dashboard removes a section when its value is ``None`` or an empty string.
    """
    if force_update is not None and not isinstance(force_update, bool):
        raise ConfigurationError("force_update must be a boolean or null.")
    data = {"name": validate_name(name), "value": validate_values(values)}
    if force_update is not None:
        data["force_update"] = force_update
    return client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)


def remove(client, name, section):
    """Remove one option's explicit value from a configuration section."""
    name = quote(validate_name(name), safe="")
    return client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{name}",
        api_version=API_VERSION,
        params={"section": validate_section(section)},
    )


def bulk_set(client, options):
    """Set one section value for each of several configuration options."""
    return client.request(
        "PUT",
        RESOURCE_PATH,
        api_version=API_VERSION,
        data={"options": validate_options(options)},
    )
