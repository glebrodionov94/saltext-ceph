"""Read operations from Dashboard's public ``summary.py`` controller."""

from collections.abc import Mapping

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/summary"


def get(client):
    """Return Dashboard's cluster, manager, task and mirroring summary."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph summary returned an unexpected response shape.")
    try:
        data = validation.json_value(response.data, "Ceph summary")
    except ConfigurationError:
        raise ProtocolError("Ceph summary returned invalid JSON data.") from None
    for key in ("health_status", "executing_tasks", "finished_tasks"):
        if key not in data:
            raise ProtocolError("Ceph summary returned an unexpected response shape.")
    if not isinstance(data["health_status"], str) or not all(
        isinstance(data[key], list) for key in ("executing_tasks", "finished_tasks")
    ):
        raise ProtocolError("Ceph summary returned an unexpected response shape.")
    return APIResponse(response.status, data, response.headers)
