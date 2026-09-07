"""Read operations from Dashboard's public ``monitor.py`` controller."""

from collections.abc import Mapping

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/monitor"


def status(client):
    """Return monitor status and quorum membership."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph monitor status returned an unexpected response shape.")
    try:
        data = validation.json_value(response.data, "Ceph monitor status")
    except ConfigurationError:
        raise ProtocolError("Ceph monitor status returned invalid JSON data.") from None
    if (
        not isinstance(data.get("mon_status"), Mapping)
        or not isinstance(data.get("in_quorum"), list)
        or not isinstance(data.get("out_quorum"), list)
    ):
        raise ProtocolError("Ceph monitor status returned an unexpected response shape.")
    return APIResponse(response.status, data, response.headers)
