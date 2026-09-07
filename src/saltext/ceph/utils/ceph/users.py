"""CephX user operations from the Dashboard ``ceph_users.py`` controller."""

import re
from collections.abc import Mapping
from collections.abc import Sequence

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/cluster/user"
_ENTITY_PATTERN = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+")


def validate_entity(entity):
    """Return a conservative, fully-qualified CephX entity name."""
    if not isinstance(entity, str) or not _ENTITY_PATTERN.fullmatch(entity):
        raise ConfigurationError("user_entity must be fully qualified, for example client.backup.")
    return entity


def validate_entities(entities):
    """Validate a non-empty sequence of unique CephX entity names."""
    if isinstance(entities, (str, bytes)) or not isinstance(entities, Sequence) or not entities:
        raise ConfigurationError("entities must be a non-empty list of CephX entity names.")
    normalized = [validate_entity(entity) for entity in entities]
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError("entities must not contain duplicates.")
    return normalized


def validate_capabilities(capabilities):
    """Validate and copy the controller's ``[{entity, cap}]`` representation."""
    if (
        isinstance(capabilities, (str, bytes))
        or not isinstance(capabilities, Sequence)
        or not capabilities
    ):
        raise ConfigurationError("capabilities must be a non-empty list.")
    normalized = []
    names = set()
    for item in capabilities:
        if not isinstance(item, Mapping) or set(item) != {"entity", "cap"}:
            raise ConfigurationError("Each capability requires only entity and cap fields.")
        entity = item["entity"]
        cap = item["cap"]
        if not isinstance(entity, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", entity):
            raise ConfigurationError("Capability entity contains unsupported characters.")
        if not isinstance(cap, str) or not cap.strip() or re.search(r"[\x00-\x1f\x7f]", cap):
            raise ConfigurationError("Capability value must be a non-empty single-line string.")
        if entity in names:
            raise ConfigurationError("Capability entities must be unique.")
        names.add(entity)
        normalized.append({"entity": entity, "cap": cap})
    return normalized


def list_(client):
    """List CephX users; Dashboard masks their keys in this response."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    if not isinstance(response.data, list):
        raise ProtocolError("Ceph user list returned an unexpected response shape.")
    data = []
    for item in response.data:
        if not isinstance(item, Mapping):
            raise ProtocolError("Ceph user list contains an invalid item.")
        normalized = dict(item)
        if "key" in normalized:
            normalized["key"] = "***********"
        data.append(normalized)
    return APIResponse(response.status, data, response.headers)


def get(client, user_entity):
    """Find one CephX user through the controller's collection endpoint."""
    user_entity = validate_entity(user_entity)
    response = list_(client)
    user = next(
        (
            item
            for item in response.data
            if isinstance(item, Mapping) and item.get("entity") == user_entity
        ),
        None,
    )
    return APIResponse(response.status, user, response.headers)


def create(client, user_entity, capabilities):
    """Create a CephX user with its complete capability set."""
    data = {
        "user_entity": validate_entity(user_entity),
        "capabilities": validate_capabilities(capabilities),
    }
    return client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)


def update(client, user_entity, capabilities):
    """Replace all capabilities of an existing CephX user."""
    data = {
        "user_entity": validate_entity(user_entity),
        "capabilities": validate_capabilities(capabilities),
    }
    return client.request("PUT", RESOURCE_PATH, api_version=API_VERSION, data=data)


def delete(client, user_entity, confirm=False):
    """Delete one CephX user after explicit confirmation."""
    validation.confirmation(confirm, "Deleting a CephX user")
    user_entity = validate_entity(user_entity)
    return client.request("DELETE", f"{RESOURCE_PATH}/{user_entity}", api_version=API_VERSION)


def import_keyring(client, keyring):
    """Import a keyring string without returning it to the caller."""
    if not isinstance(keyring, str) or not keyring.strip() or "\x00" in keyring:
        raise ConfigurationError("The keyring file is empty or invalid.")
    return client.request(
        "POST", RESOURCE_PATH, api_version=API_VERSION, data={"import_data": keyring}
    )


def export_keyring(client, entities):
    """Export keyring text for validated entities."""
    entities = validate_entities(entities)
    response = client.request(
        "POST",
        f"{RESOURCE_PATH}/export",
        api_version=API_VERSION,
        data={"entities": entities},
    )
    if not isinstance(response.data, str) or not response.data.strip():
        raise ProtocolError("Ceph keyring export returned an unexpected response shape.")
    return response
