"""Operations from Dashboard's public ``health.py`` controller."""

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/health"


def _mapping(client, endpoint, label):
    response = client.request("GET", f"{RESOURCE_PATH}/{endpoint}", api_version=API_VERSION)
    return validation.mapping_response(response, label)


def full(client):
    """Return the detailed, permission-filtered cluster health report."""
    return _mapping(client, "full", "Ceph full health report")


def minimal(client):
    """Return the compact, permission-filtered cluster health report."""
    return _mapping(client, "minimal", "Ceph minimal health report")


def capacity(client):
    """Return aggregate cluster capacity."""
    return _mapping(client, "get_cluster_capacity", "Ceph cluster capacity")


def fsid(client):
    """Return the cluster FSID."""
    response = client.request("GET", f"{RESOURCE_PATH}/get_cluster_fsid", api_version=API_VERSION)
    if not isinstance(response.data, str) or not response.data:
        raise ProtocolError("Ceph cluster FSID returned an unexpected response shape.")
    return response


def telemetry_enabled(client):
    """Return whether the telemetry manager module is enabled."""
    response = client.request(
        "GET", f"{RESOURCE_PATH}/get_telemetry_status", api_version=API_VERSION
    )
    if not isinstance(response.data, bool):
        raise ProtocolError("Ceph telemetry status returned an unexpected response shape.")
    return response


def snapshot(client):
    """Return the current-release status-like cluster health snapshot."""
    return _mapping(client, "snapshot", "Ceph health snapshot")
