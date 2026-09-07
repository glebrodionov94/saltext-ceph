"""Read the public feature-toggle controller registered by Dashboard's plugin."""

from collections.abc import Mapping

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/feature_toggles"


def list_(client):
    """Return the Dashboard feature names and their enabled status."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    if (
        not isinstance(response.data, Mapping)
        or not response.data
        or len(response.data) > 64
        or not all(
            isinstance(name, str) and name and len(name) <= 255 and isinstance(enabled, bool)
            for name, enabled in response.data.items()
        )
    ):
        raise ProtocolError("Ceph feature toggles returned an unexpected response shape.")
    return APIResponse(response.status, dict(response.data), response.headers)
