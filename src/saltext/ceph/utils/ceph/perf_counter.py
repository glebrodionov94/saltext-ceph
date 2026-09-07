"""Read operations for Dashboard performance-counter controllers."""

import re
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/perf_counters"
SERVICE_TYPES = frozenset(("mds", "mgr", "mon", "osd", "rbd-mirror", "rgw", "tcmu-runner"))
_SERVICE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,255}")


def _mapping(response, label):
    if not isinstance(response.data, Mapping):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    try:
        data = validation.json_value(response.data, label)
    except ConfigurationError:
        raise ProtocolError(f"{label} returned invalid JSON data.") from None
    return APIResponse(response.status, data, response.headers)


def list_(client):
    """Return all unlabeled performance counters."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    return _mapping(response, "Ceph performance counters")


def get(client, service_type, service_id):
    """Return performance counters for one daemon service."""
    if service_type not in SERVICE_TYPES:
        raise ConfigurationError("service_type contains an unsupported value.")
    service_id = validation.identifier(
        service_id,
        "service_id",
        pattern=_SERVICE_ID_PATTERN,
        max_length=256,
    )
    path = f"{RESOURCE_PATH}/{service_type}/{quote(service_id, safe='')}"
    response = client.request("GET", path, api_version=API_VERSION)
    return _mapping(response, "Ceph service performance counters")
