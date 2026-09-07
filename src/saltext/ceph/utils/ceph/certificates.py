"""Read-only operations from Dashboard ``certificate.py``."""

import re
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/service/certificate"
STATUSES = frozenset(("expired", "expiring", "valid", "invalid", "not_configured"))
SCOPES = frozenset(("service", "host", "global"))
_SERVICE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_TYPE_FILTER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.*?-]*")


def _enum(value, label, choices):
    if value is None:
        return None
    if not isinstance(value, str) or value.lower() not in choices:
        raise ConfigurationError(f"{label} must be one of: {', '.join(sorted(choices))}.")
    return value.lower()


def _service_name(value):
    if not isinstance(value, str) or not _SERVICE_PATTERN.fullmatch(value):
        raise ConfigurationError("service_name contains unsupported characters.")
    return value


def _service_type(value):
    if value is None:
        return None
    if not isinstance(value, str) or not _TYPE_FILTER_PATTERN.fullmatch(value):
        raise ConfigurationError("service_type contains unsupported filter characters.")
    return value.lower()


def list_(
    client,
    status=None,
    scope=None,
    service_type=None,
    include_cephadm_signed=False,
):
    """List certificate metadata with optional controller-side filters."""
    if not isinstance(include_cephadm_signed, bool):
        raise ConfigurationError("include_cephadm_signed must be a boolean.")
    params = {
        key: value
        for key, value in {
            "status": _enum(status, "status", STATUSES),
            "scope": _enum(scope, "scope", SCOPES),
            "service_type": _service_type(service_type),
            "include_cephadm_signed": True if include_cephadm_signed else None,
        }.items()
        if value is not None
    }
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION, params=params)
    if not isinstance(response.data, list) or not all(
        isinstance(item, Mapping) for item in response.data
    ):
        raise ProtocolError("Ceph certificate list returned an unexpected response shape.")
    return APIResponse(response.status, [dict(item) for item in response.data], response.headers)


def get(client, service_name):
    """Return detailed certificate status for one orchestrator service."""
    service_name = quote(_service_name(service_name), safe="")
    response = client.request("GET", f"{RESOURCE_PATH}/{service_name}", api_version=API_VERSION)
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph certificate details returned an unexpected response shape.")
    return APIResponse(response.status, dict(response.data), response.headers)


def root_ca(client):
    """Return the public cephadm root CA certificate in PEM form."""
    response = client.request("GET", f"{RESOURCE_PATH}/root-ca", api_version=API_VERSION)
    if (
        not isinstance(response.data, str)
        or "-----BEGIN CERTIFICATE-----" not in response.data
        or "-----END CERTIFICATE-----" not in response.data
    ):
        raise ProtocolError("Ceph root CA endpoint returned an invalid certificate.")
    return response
