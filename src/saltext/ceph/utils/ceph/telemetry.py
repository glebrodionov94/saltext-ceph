"""Operations from Dashboard's public ``telemetry.py`` controller."""

from collections.abc import Mapping

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/telemetry"
LICENSE = "sharing-1-0"


def report(client):
    """Return the cluster and device telemetry preview."""
    response = client.request("GET", f"{RESOURCE_PATH}/report", api_version=API_VERSION)
    if (
        not isinstance(response.data, Mapping)
        or not isinstance(response.data.get("report"), Mapping)
        or not isinstance(response.data.get("device_report"), Mapping)
    ):
        raise ProtocolError("Ceph telemetry report returned an unexpected response shape.")
    return APIResponse(response.status, dict(response.data), response.headers)


def set_(client, enable=True, license_name=None):
    """Enable or disable periodic telemetry submission."""
    if not isinstance(enable, bool):
        raise ConfigurationError("enable must be a boolean.")
    if enable and license_name != LICENSE:
        raise ConfigurationError(
            "Enabling telemetry requires explicit acceptance of license sharing-1-0."
        )
    if not enable and license_name is not None:
        raise ConfigurationError("license_name must be omitted when disabling telemetry.")
    data = {"enable": enable}
    if enable:
        data["license_name"] = license_name
    response = client.request("PUT", RESOURCE_PATH, api_version=API_VERSION, data=data)
    return APIResponse(response.status, {"enabled": enable}, response.headers)
