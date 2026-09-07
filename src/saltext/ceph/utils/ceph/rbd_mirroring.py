"""RBD mirroring operations from Dashboard's public controller."""

import re
import uuid
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/block/mirroring"
POOL_PATH = f"{RESOURCE_PATH}/pool"
POOL_MODES = frozenset(("disabled", "image", "init-only", "pool"))
DIRECTIONS = frozenset(("rx", "rx-tx"))
_SECRET_KEYS = frozenset(("key", "password", "token"))


def _name(value, label):
    return validation.identifier(value, label)


def _text(value, label, *, optional=False, allow_empty=False, max_length=4096):
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or len(value) > max_length
        or (not value and not allow_empty)
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError(f"{label} must be bounded single-line text.")
    return value


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _confirmed(value, action):
    _boolean(value, "confirm")
    if not value:
        raise ConfigurationError(f"{action} requires confirm=True.")


def _peer_uuid(value):
    if not isinstance(value, str):
        raise ConfigurationError("peer_uuid must be a canonical UUID.")
    try:
        normalized = str(uuid.UUID(value))
    except ValueError:
        raise ConfigurationError("peer_uuid must be a canonical UUID.") from None
    if value.lower() != normalized:
        raise ConfigurationError("peer_uuid must be a canonical UUID.")
    return normalized


def _pool_path(pool_name, suffix=None):
    path = f"{POOL_PATH}/{quote(_name(pool_name, 'pool_name'), safe='')}"
    return f"{path}/{suffix}" if suffix else path


def _peer_path(pool_name, peer_uuid=None):
    path = _pool_path(pool_name, "peer")
    if peer_uuid is not None:
        path = f"{path}/{quote(_peer_uuid(peer_uuid), safe='')}"
    return path


def _strip_secrets(value):
    if isinstance(value, Mapping):
        return {
            key: _strip_secrets(child)
            for key, child in value.items()
            if str(key).lower() not in _SECRET_KEYS
        }
    if isinstance(value, list):
        return [_strip_secrets(child) for child in value]
    return value


def _safe_response(response):
    return APIResponse(response.status, _strip_secrets(response.data), response.headers)


def _mapping_response(response, label):
    response = validation.mapping_response(response, label)
    return _safe_response(response)


def summary(client):
    """Return the cluster-wide RBD mirroring summary."""
    response = client.request("GET", f"{RESOURCE_PATH}/summary", api_version=API_VERSION)
    return _mapping_response(response, "Ceph RBD mirroring summary")


def image_summary(client, pool_name, image_name):
    """Return image mirroring status from the current-main-only endpoint."""
    pool_name = quote(_name(pool_name, "pool_name"), safe="")
    image_name = quote(_name(image_name, "image_name"), safe="")
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/{pool_name}/{image_name}/summary",
        api_version=API_VERSION,
    )
    return _mapping_response(response, "Ceph RBD image mirroring summary")


def get_site_name(client):
    """Return the local mirroring site name."""
    response = client.request("GET", f"{RESOURCE_PATH}/site_name", api_version=API_VERSION)
    response = _mapping_response(response, "Ceph RBD mirroring site")
    if not isinstance(response.data.get("site_name"), str):
        raise ProtocolError("Ceph RBD mirroring site returned no site_name.")
    return response


def set_site_name(client, site_name):
    """Set the local friendly mirroring site name."""
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/site_name",
        api_version=API_VERSION,
        data={"site_name": _text(site_name, "site_name", max_length=255)},
    )
    return _safe_response(response)


def get_pool_mode(client, pool_name):
    """Return a pool's configured mirroring mode."""
    response = client.request("GET", _pool_path(pool_name), api_version=API_VERSION)
    response = _mapping_response(response, "Ceph RBD pool mirroring mode")
    if not isinstance(response.data.get("mirror_mode"), str):
        raise ProtocolError("Ceph RBD pool mirroring mode returned no mirror_mode.")
    return response


def set_pool_mode(client, pool_name, mirror_mode, confirm=False):
    """Set a pool mirroring mode; disabling requires confirmation."""
    if not isinstance(mirror_mode, str) or mirror_mode not in POOL_MODES:
        raise ConfigurationError(f"mirror_mode must be one of: {', '.join(sorted(POOL_MODES))}.")
    _boolean(confirm, "confirm")
    if mirror_mode == "disabled":
        _confirmed(confirm, "Disabling RBD pool mirroring")
    return client.request(
        "PUT",
        _pool_path(pool_name),
        api_version=API_VERSION,
        data={"mirror_mode": mirror_mode},
    )


def create_bootstrap_token(client, pool_name):
    """Create a bootstrap token for immediate storage by the composition layer."""
    response = client.request(
        "POST",
        _pool_path(pool_name, "bootstrap/token"),
        api_version=API_VERSION,
        data={},
    )
    if (
        not isinstance(response.data, Mapping)
        or not isinstance(response.data.get("token"), str)
        or not response.data["token"].strip()
        or re.search(r"\s", response.data["token"])
    ):
        raise ProtocolError("Ceph RBD bootstrap endpoint returned no usable token.")
    return APIResponse(response.status, {"token": response.data["token"]}, response.headers)


def import_bootstrap_token(client, pool_name, direction, token):
    """Import a peer bootstrap token and discard the response body."""
    if direction not in DIRECTIONS:
        raise ConfigurationError(f"direction must be one of: {', '.join(sorted(DIRECTIONS))}.")
    token = _text(token, "token")
    response = client.request(
        "POST",
        _pool_path(pool_name, "bootstrap/peer"),
        api_version=API_VERSION,
        data={"direction": direction, "token": token},
    )
    return APIResponse(response.status, {"pool_name": pool_name}, response.headers)


def list_peers(client, pool_name):
    """List peer UUIDs registered for a pool."""
    response = client.request("GET", _peer_path(pool_name), api_version=API_VERSION)
    if not isinstance(response.data, list) or not all(
        isinstance(item, str) for item in response.data
    ):
        raise ProtocolError("Ceph RBD mirroring peer list returned an unexpected response shape.")
    return APIResponse(response.status, list(response.data), response.headers)


def get_peer(client, pool_name, peer_uuid):
    """Return public peer metadata with CephX keys removed."""
    response = client.request("GET", _peer_path(pool_name, peer_uuid), api_version=API_VERSION)
    return _mapping_response(response, "Ceph RBD mirroring peer")


def create_peer(client, pool_name, cluster_name, client_id, mon_host=None, key=None):
    """Create a legacy peer, optionally with a file-sourced key."""
    data = {
        "cluster_name": _name(cluster_name, "cluster_name"),
        "client_id": _name(client_id, "client_id"),
    }
    if mon_host is not None:
        data["mon_host"] = _text(mon_host, "mon_host", allow_empty=True)
    if key is not None:
        data["key"] = _text(key, "key")
    response = client.request("POST", _peer_path(pool_name), api_version=API_VERSION, data=data)
    response = _mapping_response(response, "Ceph RBD mirroring peer creation")
    if not isinstance(response.data.get("uuid"), str):
        raise ProtocolError("Ceph RBD mirroring peer creation returned no uuid.")
    return response


def update_peer(
    client,
    pool_name,
    peer_uuid,
    cluster_name=None,
    client_id=None,
    mon_host=None,
    key=None,
):
    """Update legacy peer attributes, accepting an already protected key value."""
    data = {}
    if cluster_name is not None:
        data["cluster_name"] = _name(cluster_name, "cluster_name")
    if client_id is not None:
        data["client_id"] = _name(client_id, "client_id")
    if mon_host is not None:
        data["mon_host"] = _text(mon_host, "mon_host", allow_empty=True)
    if key is not None:
        data["key"] = _text(key, "key", allow_empty=True)
    if not data:
        raise ConfigurationError("At least one peer update value must be provided.")
    response = client.request(
        "PUT", _peer_path(pool_name, peer_uuid), api_version=API_VERSION, data=data
    )
    return _safe_response(response)


def delete_peer(client, pool_name, peer_uuid, confirm=False):
    """Remove a mirroring peer after confirmation."""
    _confirmed(confirm, "Deleting an RBD mirroring peer")
    response = client.request("DELETE", _peer_path(pool_name, peer_uuid), api_version=API_VERSION)
    return _safe_response(response)
