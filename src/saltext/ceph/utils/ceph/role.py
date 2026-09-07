"""Operations from Dashboard's public ``role.py`` controller."""

import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import ConfigurationError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/role"
PERMISSIONS = frozenset(("read", "create", "update", "delete"))
_ROLE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}")


def validate_name(value, label="name"):
    """Validate a role name that can safely occupy one API path segment."""
    return validation.identifier(value, label, pattern=_ROLE_PATTERN, max_length=255)


def validate_description(value):
    """Validate an optional, bounded role description."""
    if value is not None and (not isinstance(value, str) or len(value) > 4096 or "\x00" in value):
        raise ConfigurationError("description must be a string of at most 4096 characters.")
    return value


def validate_scopes_permissions(value):
    """Copy a complete scope-to-permissions mapping accepted by Dashboard."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ConfigurationError("scopes_permissions must be a mapping.")
    result = {}
    for scope, permissions in value.items():
        scope = validation.identifier(scope, "scope")
        if isinstance(permissions, (str, bytes)) or not isinstance(permissions, Sequence):
            raise ConfigurationError("Each role scope must contain a list of permissions.")
        permissions = list(permissions)
        if any(not isinstance(item, str) or item not in PERMISSIONS for item in permissions):
            raise ConfigurationError("Role permissions must be read, create, update, or delete.")
        if len(set(permissions)) != len(permissions):
            raise ConfigurationError("Role permissions must not contain duplicates.")
        result[scope] = permissions
    return result


def _mapping(response, operation):
    return validation.mapping_response(response, f"Ceph role {operation}")


def list_(client):
    """List custom and built-in Dashboard roles."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    return validation.mapping_list_response(response, "Ceph role list")


def get(client, name):
    """Return one Dashboard role."""
    name = validate_name(name)
    response = client.request(
        "GET", f"{RESOURCE_PATH}/{quote(name, safe='')}", api_version=API_VERSION
    )
    return _mapping(response, "get")


def create(client, name, description=None, scopes_permissions=None):
    """Create a Dashboard role."""
    data = {
        "name": validate_name(name),
        "description": validate_description(description),
        "scopes_permissions": validate_scopes_permissions(scopes_permissions),
    }
    return _mapping(
        client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data),
        "create",
    )


def update(client, name, description=None, scopes_permissions=None):
    """Replace a custom role's description and complete permission mapping."""
    name = validate_name(name)
    data = {
        "description": validate_description(description),
        "scopes_permissions": validate_scopes_permissions(scopes_permissions),
    }
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/{quote(name, safe='')}",
        api_version=API_VERSION,
        data=data,
    )
    return _mapping(response, "update")


def delete(client, name, confirm=False):
    """Delete a custom Dashboard role after explicit confirmation."""
    validation.confirmation(confirm, "Deleting a Dashboard role")
    name = validate_name(name)
    return client.request(
        "DELETE", f"{RESOURCE_PATH}/{quote(name, safe='')}", api_version=API_VERSION
    )


def clone(client, name, new_name):
    """Clone a Dashboard role under a new name."""
    name = validate_name(name)
    data = {"new_name": validate_name(new_name, "new_name")}
    response = client.request(
        "POST",
        f"{RESOURCE_PATH}/{quote(name, safe='')}/clone",
        api_version=API_VERSION,
        data=data,
    )
    return _mapping(response, "clone")
