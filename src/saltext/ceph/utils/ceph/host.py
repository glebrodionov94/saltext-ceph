"""Operations from Dashboard's public ``host.py`` controller."""

import re
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import ConfigurationError

LIST_API_VERSION = "1.3"
GET_API_VERSION = "1.2"
DEFAULT_API_VERSION = "1.0"
EXPERIMENTAL_API_VERSION = "0.1"
RESOURCE_PATH = "/api/host"
SOURCES = frozenset(("ceph", "orchestrator"))
_LABEL_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_SORT_PATTERN = re.compile(r"[+-]?hostname")


def _hostname(value):
    return validation.identifier(value, "hostname")


def _labels(values, optional=True):
    if values is None and optional:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ConfigurationError("labels must be a list of strings.")
    normalized = []
    for value in values:
        normalized.append(validation.identifier(value, "labels", pattern=_LABEL_PATTERN))
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError("labels must not contain duplicates.")
    return normalized


def _optional_text(value, label, max_length=255):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError(f"{label} must be a non-empty text value.")
    return value


validate_hostname = _hostname
validate_labels = _labels
validate_optional_text = _optional_text


def _resource_path(hostname, suffix=None):
    path = f"{RESOURCE_PATH}/{quote(_hostname(hostname), safe='')}"
    return f"{path}/{suffix}" if suffix else path


def list_(
    client,
    sources=None,
    facts=False,
    offset=0,
    limit=-1,
    search="",
    sort="+hostname",
    include_service_instances=True,
):
    """List hosts with optional source, facts, pagination, and service filters."""
    sources = validation.string_list(sources, "sources", allowed=SOURCES, optional=True)
    for label, value in {
        "facts": facts,
        "include_service_instances": include_service_instances,
    }.items():
        if not isinstance(value, bool):
            raise ConfigurationError(f"{label} must be a boolean.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ConfigurationError("offset must be a non-negative integer.")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < -1:
        raise ConfigurationError("limit must be -1 or a non-negative integer.")
    if not isinstance(search, str) or len(search) > 255 or re.search(r"[\x00-\x1f\x7f]", search):
        raise ConfigurationError("search must be a bounded text value.")
    if not isinstance(sort, str) or not _SORT_PATTERN.fullmatch(sort):
        raise ConfigurationError("sort must be hostname, +hostname, or -hostname.")
    params = {
        "facts": facts,
        "offset": offset,
        "limit": limit,
        "search": search,
        "sort": sort,
        "include_service_instances": include_service_instances,
    }
    if sources is not None:
        params["sources"] = ",".join(sources)
    response = client.request("GET", RESOURCE_PATH, api_version=LIST_API_VERSION, params=params)
    return validation.mapping_list_response(response, "Ceph host list")


def get(client, hostname):
    """Return one host."""
    response = client.request("GET", _resource_path(hostname), api_version=GET_API_VERSION)
    return validation.mapping_response(response, "Ceph host")


def create(client, hostname, address=None, labels=None, maintenance=False):
    """Add a host to the orchestrator, optionally entering maintenance."""
    if not isinstance(maintenance, bool):
        raise ConfigurationError("maintenance must be a boolean.")
    data = {"hostname": _hostname(hostname)}
    address = _optional_text(address, "address")
    labels = _labels(labels)
    if address is not None:
        data["addr"] = address
    if labels is not None:
        data["labels"] = labels
    if maintenance:
        data["status"] = "maintenance"
    return client.request("POST", RESOURCE_PATH, api_version=EXPERIMENTAL_API_VERSION, data=data)


def delete(client, hostname, confirm=False):
    """Remove a host from the orchestrator after confirmation."""
    validation.confirmation(confirm, "Deleting a cephadm host")
    return client.request("DELETE", _resource_path(hostname), api_version=DEFAULT_API_VERSION)


def set_labels(client, hostname, labels):
    """Replace all orchestrator labels on a host."""
    return client.request(
        "PUT",
        _resource_path(hostname),
        api_version=EXPERIMENTAL_API_VERSION,
        data={"update_labels": True, "labels": _labels(labels, optional=False)},
    )


def toggle_maintenance(client, hostname, force=False):
    """Toggle host maintenance mode using the controller's toggle operation."""
    if not isinstance(force, bool):
        raise ConfigurationError("force must be a boolean.")
    data = {"maintenance": True}
    if force:
        data["force"] = True
    return client.request(
        "PUT",
        _resource_path(hostname),
        api_version=EXPERIMENTAL_API_VERSION,
        data=data,
    )


def drain(client, hostname):
    """Schedule removal of orchestrated daemons from a host."""
    return client.request(
        "PUT",
        _resource_path(hostname),
        api_version=EXPERIMENTAL_API_VERSION,
        data={"drain": True},
    )


def devices(client, hostname):
    """Return Ceph devices associated with a host."""
    response = client.request(
        "GET", _resource_path(hostname, "devices"), api_version=DEFAULT_API_VERSION
    )
    return validation.mapping_list_response(response, "Ceph host device list")


def smart(client, hostname):
    """Return SMART data for devices associated with a host."""
    response = client.request(
        "GET", _resource_path(hostname, "smart"), api_version=DEFAULT_API_VERSION
    )
    return validation.mapping_response(response, "Ceph host SMART data")


def inventory(client, hostname, refresh=False):
    """Return orchestrator device inventory for one host."""
    if not isinstance(refresh, bool):
        raise ConfigurationError("refresh must be a boolean.")
    response = client.request(
        "GET",
        _resource_path(hostname, "inventory"),
        api_version=DEFAULT_API_VERSION,
        params={"refresh": refresh},
    )
    return validation.mapping_response(response, "Ceph host inventory")


def identify_device(client, hostname, device, duration=10):
    """Blink a device identification LED for a bounded duration."""
    device = _optional_text(device, "device", max_length=512)
    if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 3600:
        raise ConfigurationError("duration must be an integer from 1 through 3600 seconds.")
    return client.request(
        "POST",
        _resource_path(hostname, "identify_device"),
        api_version=DEFAULT_API_VERSION,
        data={"device": device, "duration": duration},
    )


def daemons(client, hostname):
    """Return orchestrated daemons placed on a host."""
    response = client.request(
        "GET", _resource_path(hostname, "daemons"), api_version=DEFAULT_API_VERSION
    )
    return validation.mapping_list_response(response, "Ceph host daemon list")
