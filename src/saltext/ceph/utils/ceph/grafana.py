"""Operations from Dashboard's public ``grafana.py`` controller."""

import re
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/grafana"
_DASHBOARD_UID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}")


def _mapping(response, operation):
    if not isinstance(response.data, Mapping):
        raise ProtocolError(f"Ceph Grafana {operation} returned an unexpected response shape.")
    return APIResponse(response.status, dict(response.data), response.headers)


def _dashboard_uid(value):
    if not isinstance(value, str) or not _DASHBOARD_UID_PATTERN.fullmatch(value):
        raise ConfigurationError("dashboard_uid contains unsupported characters.")
    return value


def url(client):
    """Return the Grafana frontend URL exposed by Dashboard."""
    response = client.request("GET", f"{RESOURCE_PATH}/url", api_version=API_VERSION)
    response = _mapping(response, "URL query")
    if not isinstance(response.data.get("instance"), str):
        raise ProtocolError("Ceph Grafana URL query returned no instance string.")
    return response


def validate_dashboard(client, dashboard_uid):
    """Ask Dashboard to check one Grafana dashboard UID."""
    dashboard_uid = quote(_dashboard_uid(dashboard_uid), safe="")
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/validation/{dashboard_uid}",
        api_version=API_VERSION,
    )
    if (
        isinstance(response.data, bool)
        or not isinstance(response.data, int)
        or not 100 <= response.data <= 599
    ):
        raise ProtocolError("Ceph Grafana validation returned an invalid HTTP status code.")
    return response


def push_dashboards(client):
    """Push Dashboard's local Ceph dashboards to its configured Grafana."""
    response = client.request(
        "POST", f"{RESOURCE_PATH}/dashboards", api_version=API_VERSION, data={}
    )
    response = _mapping(response, "dashboard push")
    if not isinstance(response.data.get("success"), bool):
        raise ProtocolError("Ceph Grafana dashboard push returned no success flag.")
    return response
