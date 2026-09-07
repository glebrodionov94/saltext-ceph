"""CephFS snapshot mirroring operations from current Dashboard ``cephfs.py``."""

import uuid
from collections.abc import Mapping

from saltext.ceph.utils.ceph import cephfs
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.utils.ceph.users import validate_entity

API_VERSION = cephfs.API_VERSION
RESOURCE_PATH = "/api/cephfs/mirror"


def _fs(value, route=False):
    if route:
        return cephfs.route_name(value, "filesystem")
    return cephfs.name(value, "filesystem")


def _uuid(value):
    if not isinstance(value, str):
        raise ConfigurationError("peer_uuid must be a UUID string.")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise ConfigurationError("peer_uuid must be a UUID string.") from None


def peer_list(client, filesystem):
    """List snapshot mirror peers for a CephFS filesystem."""
    return client.request(
        "GET", f"{RESOURCE_PATH}/{_fs(filesystem, route=True)}", api_version=API_VERSION
    )


def enable(client, filesystem):
    """Enable snapshot mirroring for a CephFS filesystem."""
    return client.request(
        "POST",
        f"{RESOURCE_PATH}/enable",
        api_version=API_VERSION,
        data={"fs_name": _fs(filesystem)},
    )


def disable(client, filesystem, confirm=False):
    """Disable CephFS snapshot mirroring after explicit confirmation."""
    cephfs.confirmed(confirm, "Disabling CephFS snapshot mirroring")
    return client.request(
        "POST",
        f"{RESOURCE_PATH}/disable",
        api_version=API_VERSION,
        data={"fs_name": _fs(filesystem)},
    )


def create_token(client, filesystem, client_name, site_name):
    """Create a bootstrap token for a CephFS snapshot mirror peer."""
    data = {
        "fs_name": _fs(filesystem),
        "client_name": validate_entity(client_name),
        "site_name": cephfs.name(site_name, "site_name"),
    }
    response = client.request("POST", f"{RESOURCE_PATH}/token", api_version=API_VERSION, data=data)
    if (
        not isinstance(response.data, Mapping)
        or not isinstance(response.data.get("token"), str)
        or not response.data["token"]
    ):
        raise ProtocolError("Ceph mirror token endpoint returned an unexpected response shape.")
    return response


def add_peer(client, filesystem, token):
    """Add a CephFS snapshot mirror peer from a bootstrap token."""
    if not isinstance(token, str) or not token.strip() or "\x00" in token:
        raise ConfigurationError("The bootstrap token file is empty or invalid.")
    return client.request(
        "POST",
        RESOURCE_PATH,
        api_version=API_VERSION,
        data={"fs_name": _fs(filesystem), "token": token.strip()},
    )


def remove_peer(client, filesystem, peer_uuid, confirm=False):
    """Remove a CephFS snapshot mirror peer after explicit confirmation."""
    cephfs.confirmed(confirm, "Removing a CephFS mirror peer")
    filesystem = _fs(filesystem, route=True)
    return client.request(
        "DELETE", f"{RESOURCE_PATH}/{filesystem}/{_uuid(peer_uuid)}", api_version=API_VERSION
    )


def add_directory(client, filesystem, path):
    """Add a CephFS directory to snapshot mirroring."""
    data = {"fs_name": _fs(filesystem), "path": cephfs.filesystem_path(path)}
    return client.request("POST", f"{RESOURCE_PATH}/directory", api_version=API_VERSION, data=data)


def remove_directory(client, filesystem, path, confirm=False):
    """Remove a directory from snapshot mirroring after confirmation."""
    cephfs.confirmed(confirm, "Removing a CephFS mirrored directory")
    params = {"fs_name": _fs(filesystem), "path": cephfs.filesystem_path(path)}
    return client.request(
        "DELETE", f"{RESOURCE_PATH}/directory", api_version=API_VERSION, params=params
    )


def directory_list(client, filesystem):
    """List directories mirrored for a CephFS filesystem."""
    return client.request(
        "GET",
        f"{RESOURCE_PATH}/directory/{_fs(filesystem, route=True)}",
        api_version=API_VERSION,
    )


def checkpoint_list(client, filesystem, path):
    """List mirror checkpoints for a CephFS directory."""
    filesystem = _fs(filesystem, route=True)
    return client.request(
        "GET",
        f"{RESOURCE_PATH}/{filesystem}/checkpoint",
        api_version=API_VERSION,
        params={"path": cephfs.filesystem_path(path)},
    )


def add_checkpoint(client, filesystem, path, snapshot):
    """Add a named mirror checkpoint for a CephFS directory."""
    filesystem = _fs(filesystem, route=True)
    data = {
        "path": cephfs.filesystem_path(path),
        "snap_name": cephfs.name(snapshot, "snapshot"),
    }
    return client.request(
        "POST",
        f"{RESOURCE_PATH}/{filesystem}/checkpoint",
        api_version=API_VERSION,
        data=data,
    )


def checkpoint_now(client, filesystem, path):
    """Create an immediate mirror checkpoint for a CephFS directory."""
    filesystem = _fs(filesystem, route=True)
    return client.request(
        "POST",
        f"{RESOURCE_PATH}/{filesystem}/checkpoint/now",
        api_version=API_VERSION,
        data={"path": cephfs.filesystem_path(path)},
    )


def remove_checkpoint(client, filesystem, path, snapshot, confirm=False):
    """Remove a CephFS mirror checkpoint after explicit confirmation."""
    cephfs.confirmed(confirm, "Removing a CephFS mirror checkpoint")
    filesystem = _fs(filesystem, route=True)
    params = {
        "path": cephfs.filesystem_path(path),
        "snap_name": cephfs.name(snapshot, "snapshot"),
    }
    return client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{filesystem}/checkpoint",
        api_version=API_VERSION,
        params=params,
    )


def daemon_status(client):
    """Get CephFS snapshot mirror daemon status."""
    return client.request("GET", f"{RESOURCE_PATH}/daemon/status", api_version=API_VERSION)


def status(client, filesystem, path=None, peer_uuid=None):
    """Get snapshot mirror status, optionally scoped by path or peer."""
    filesystem = _fs(filesystem, route=True)
    params = cephfs.optional_params(
        path=None if path in (None, "") else cephfs.filesystem_path(path),
        peer_id=None if peer_uuid in (None, "") else _uuid(peer_uuid),
    )
    return client.request(
        "GET",
        f"{RESOURCE_PATH}/{filesystem}/status",
        api_version=API_VERSION,
        params=params,
    )


def without_token(response):
    """Return safe metadata from a token response."""
    if not isinstance(response, APIResponse) or not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph mirror token response is invalid.")
    return APIResponse(response.status, {"token_saved": True}, response.headers)
