"""Operations from Dashboard's public ``service.py`` controller."""

import math
import re
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

LIST_API_VERSION = "2.0"
API_VERSION = "1.0"
RESOURCE_PATH = "/api/service"
_SERVICE_TYPE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_SORT_PATTERN = re.compile(r"[+-]?(?:service_name|status\.(?:running|last_refreshed|size))")


def _service_name(value, label="service_name"):
    return validation.identifier(value, label)


def _json_value(value, label, depth=0):
    """Copy a JSON-compatible value without flattening a ServiceSpec."""
    if depth > 32:
        raise ConfigurationError(f"{label} is nested too deeply.")
    if isinstance(value, Mapping):
        normalized = {}
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or not key
                or len(key) > 255
                or re.search(r"[\x00-\x1f\x7f]", key)
            ):
                raise ConfigurationError(f"{label} contains an invalid mapping key.")
            normalized[key] = _json_value(item, f"{label}[{key!r}]", depth + 1)
        return normalized
    if isinstance(value, list):
        return [
            _json_value(item, f"{label}[{index}]", depth + 1) for index, item in enumerate(value)
        ]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ConfigurationError(f"{label} must contain only finite numbers.")
        return value
    raise ConfigurationError(f"{label} must contain only JSON-compatible values.")


def _service_spec(value, service_name):
    if not isinstance(value, Mapping) or not value:
        raise ConfigurationError("service_spec must be a non-empty mapping.")
    spec = _json_value(value, "service_spec")

    spec_name = spec.get("service_name")
    if spec_name is not None:
        spec_name = _service_name(spec_name, "service_spec service_name")

    service_type = spec.get("service_type")
    service_id = spec.get("service_id")
    derived_name = None
    if service_type is not None:
        if not isinstance(service_type, str) or not _SERVICE_TYPE_PATTERN.fullmatch(service_type):
            raise ConfigurationError("service_spec service_type contains unsupported characters.")
        derived_name = service_type
        if service_id is not None:
            service_id = _service_name(service_id, "service_spec service_id")
            derived_name = f"{service_type}.{service_id}"
    elif service_id is not None:
        raise ConfigurationError("service_spec service_id requires service_type.")

    if spec_name is None and derived_name is None:
        raise ConfigurationError("service_spec requires service_type or service_name.")
    if spec_name is not None and derived_name is not None and spec_name != derived_name:
        raise ConfigurationError(
            "service_spec service_name does not match service_type and service_id."
        )
    if service_name != (spec_name or derived_name):
        raise ConfigurationError("service_name does not match the ServiceSpec identity.")
    return spec


validate_service_name = _service_name
validate_service_spec = _service_spec


def _text(value, label):
    if not isinstance(value, str) or len(value) > 255 or re.search(r"[\x00-\x1f\x7f]", value):
        raise ConfigurationError(f"{label} must be a bounded text value.")
    return value


def list_(
    client,
    service_name=None,
    offset=0,
    limit=-1,
    search="",
    sort="+service_name",
):
    """List orchestrator services, returning all matching services by default."""
    if service_name is not None:
        service_name = _service_name(service_name)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ConfigurationError("offset must be a non-negative integer.")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < -1:
        raise ConfigurationError("limit must be -1 or a non-negative integer.")
    search = _text(search, "search")
    if not isinstance(sort, str) or not _SORT_PATTERN.fullmatch(sort):
        raise ConfigurationError("sort must select service_name or a supported status field.")
    params = {
        "offset": offset,
        "limit": limit,
        "search": search,
        "sort": sort,
    }
    if service_name is not None:
        params["service_name"] = service_name
    response = client.request("GET", RESOURCE_PATH, api_version=LIST_API_VERSION, params=params)
    return validation.mapping_list_response(response, "Ceph service list")


def get(client, service_name):
    """Return one orchestrator service."""
    service_name = quote(_service_name(service_name), safe="")
    response = client.request("GET", f"{RESOURCE_PATH}/{service_name}", api_version=API_VERSION)
    return validation.mapping_response(response, "Ceph service")


def known_types(client):
    """Return the service types known to this Ceph release."""
    response = client.request("GET", f"{RESOURCE_PATH}/known_types", api_version=API_VERSION)
    if not isinstance(response.data, list) or not all(
        isinstance(item, str) and item for item in response.data
    ):
        raise ProtocolError("Ceph known service types returned an unexpected response shape.")
    return APIResponse(response.status, list(response.data), response.headers)


def daemons(client, service_name):
    """Return daemons belonging to one orchestrator service."""
    service_name = quote(_service_name(service_name), safe="")
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/{service_name}/daemons",
        api_version=API_VERSION,
    )
    return validation.mapping_list_response(response, "Ceph service daemon list")


def create(client, service_name, service_spec):
    """Create a service without overwriting an existing ServiceSpec."""
    service_name = _service_name(service_name)
    data = {
        "service_name": service_name,
        "service_spec": _service_spec(service_spec, service_name),
    }
    return client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)


def update(client, service_name, service_spec):
    """Replace the declarative ServiceSpec for an existing service."""
    service_name = _service_name(service_name)
    data = {"service_spec": _service_spec(service_spec, service_name)}
    return client.request(
        "PUT",
        f"{RESOURCE_PATH}/{quote(service_name, safe='')}",
        api_version=API_VERSION,
        data=data,
    )


def delete(client, service_name, confirm=False):
    """Remove a service and its daemons after explicit confirmation."""
    validation.confirmation(confirm, "Deleting a cephadm service")
    service_name = quote(_service_name(service_name), safe="")
    return client.request("DELETE", f"{RESOURCE_PATH}/{service_name}", api_version=API_VERSION)
