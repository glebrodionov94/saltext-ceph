"""Operations from Dashboard's public ``crush_rule.py`` controller."""

import re
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

READ_API_VERSION = "2.0"
WRITE_API_VERSION = "1.0"
RESOURCE_PATH = "/api/crush_rule"
POOL_TYPES = frozenset(("replication", "erasure"))
_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _name(value, label, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _NAME_PATTERN.fullmatch(value):
        raise ConfigurationError(f"{label} contains unsupported characters.")
    return value


def _rule_list(response):
    if not isinstance(response.data, list) or not all(
        isinstance(item, Mapping) for item in response.data
    ):
        raise ProtocolError("Ceph CRUSH rule list returned an unexpected response shape.")
    return APIResponse(response.status, [dict(item) for item in response.data], response.headers)


def list_(client):
    """Return all CRUSH rules from the current OSD map."""
    response = client.request("GET", RESOURCE_PATH, api_version=READ_API_VERSION)
    return _rule_list(response)


def get(client, name):
    """Return one CRUSH rule by name."""
    name = quote(_name(name, "name"), safe="")
    response = client.request("GET", f"{RESOURCE_PATH}/{name}", api_version=READ_API_VERSION)
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph CRUSH rule get returned an unexpected response shape.")
    return APIResponse(response.status, dict(response.data), response.headers)


def build_create_payload(
    name,
    failure_domain,
    device_class=None,
    root=None,
    erasure_profile=None,
    pool_type="replication",
):
    """Validate and return Dashboard's CRUSH rule creation body."""
    name = _name(name, "name")
    failure_domain = _name(failure_domain, "failure_domain")
    device_class = _name(device_class, "device_class", optional=True)
    root = _name(root, "root", optional=True)
    erasure_profile = _name(erasure_profile, "erasure_profile", optional=True)
    if not isinstance(pool_type, str) or pool_type.lower() not in POOL_TYPES:
        raise ConfigurationError(f"pool_type must be one of: {', '.join(sorted(POOL_TYPES))}.")
    pool_type = pool_type.lower()
    if pool_type == "replication":
        if root is None:
            raise ConfigurationError("root is required for a replicated CRUSH rule.")
        if erasure_profile is not None:
            raise ConfigurationError("erasure_profile is only valid for an erasure CRUSH rule.")
    elif root is not None:
        raise ConfigurationError("root is only valid for a replicated CRUSH rule.")

    data = {
        "name": name,
        "failure_domain": failure_domain,
    }
    for key, value in {
        "device_class": device_class,
        "root": root,
        "profile": erasure_profile,
    }.items():
        if value is not None:
            data[key] = value
    if pool_type == "erasure":
        data["pool_type"] = pool_type
    return data


def create(
    client,
    name,
    failure_domain,
    device_class=None,
    root=None,
    erasure_profile=None,
    pool_type="replication",
):
    """Create a replicated rule or, on current Ceph, an erasure rule."""
    data = build_create_payload(
        name,
        failure_domain,
        device_class,
        root,
        erasure_profile,
        pool_type,
    )
    return client.request("POST", RESOURCE_PATH, api_version=WRITE_API_VERSION, data=data)


validate_rule_name = _name


def delete(client, name, confirm=False):
    """Delete one CRUSH rule by name after explicit confirmation."""
    validation.confirmation(confirm, "Deleting a CRUSH rule")
    name = quote(_name(name, "name"), safe="")
    return client.request("DELETE", f"{RESOURCE_PATH}/{name}", api_version=WRITE_API_VERSION)
