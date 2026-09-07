"""Read operations from Dashboard's public ``logs.py`` controller."""

from collections.abc import Mapping

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/logs/all"


def all_(client):
    """Return Dashboard's bounded cluster and audit log buffers."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph logs returned an unexpected response shape.")
    try:
        data = validation.json_value(response.data, "Ceph logs")
    except ConfigurationError:
        raise ProtocolError("Ceph logs returned invalid JSON data.") from None
    if not isinstance(data.get("clog"), list) or not isinstance(data.get("audit_log"), list):
        raise ProtocolError("Ceph logs returned an unexpected response shape.")
    return APIResponse(response.status, data, response.headers)
