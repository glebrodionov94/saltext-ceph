"""Salt-facing composition for RBD mirroring with explicit secret files."""

import os
from pathlib import Path

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rbd_mirroring
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import ConfigurationError

OPERATIONS = {
    "summary": rbd_mirroring.summary,
    "image_summary": rbd_mirroring.image_summary,
    "get_site_name": rbd_mirroring.get_site_name,
    "set_site_name": rbd_mirroring.set_site_name,
    "get_pool_mode": rbd_mirroring.get_pool_mode,
    "set_pool_mode": rbd_mirroring.set_pool_mode,
    "list_peers": rbd_mirroring.list_peers,
    "get_peer": rbd_mirroring.get_peer,
    "delete_peer": rbd_mirroring.delete_peer,
}


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def _secret(source, label):
    value = secret_file.read(source).rstrip("\r\n")
    if not value:
        raise ConfigurationError(f"{label} file contains only line separators.")
    return value


def _destination(destination, overwrite):
    if not isinstance(destination, (str, os.PathLike)):
        raise ConfigurationError("destination must be a filesystem path.")
    if not isinstance(overwrite, bool):
        raise ConfigurationError("overwrite must be a boolean.")
    path = Path(destination)
    if (
        not path.is_absolute()
        or not path.parent.is_dir()
        or path.is_symlink()
        or (path.exists() and not path.is_file())
    ):
        raise ConfigurationError(
            "destination must be an absolute file path in an existing directory."
        )
    if path.exists() and not overwrite:
        raise ConfigurationError("destination already exists; set overwrite=True to replace it.")
    return str(path)


def call(opts, pillar, context, operation, *args, profile="default", **kwargs):
    """Invoke a non-secret RBD mirroring operation."""
    try:
        function = OPERATIONS[operation]
    except KeyError:
        raise ConfigurationError("Unknown RBD mirroring operation.") from None
    return function(_client(opts, pillar, context, profile), *args, **kwargs).as_dict()


def create_bootstrap_token(
    opts,
    pillar,
    context,
    pool_name,
    destination,
    overwrite=False,
    profile="default",
):
    """Create a bootstrap token and save it without returning it to Salt."""
    destination = _destination(destination, overwrite)
    response = rbd_mirroring.create_bootstrap_token(
        _client(opts, pillar, context, profile), pool_name
    )
    path = secret_file.write(destination, response.data["token"], overwrite=overwrite)
    return {
        "status": response.status,
        "data": {"pool_name": pool_name, "destination": path},
        "headers": response.headers,
    }


def import_bootstrap_token(
    opts,
    pillar,
    context,
    pool_name,
    source,
    direction="rx-tx",
    profile="default",
):
    """Import a bootstrap token from an absolute local file."""
    token = _secret(source, "Bootstrap token")
    response = rbd_mirroring.import_bootstrap_token(
        _client(opts, pillar, context, profile),
        pool_name,
        direction,
        token,
    )
    return response.as_dict()


def create_peer(
    opts,
    pillar,
    context,
    pool_name,
    cluster_name,
    client_id,
    mon_host=None,
    key_source=None,
    profile="default",
):
    """Create a legacy peer, reading an optional CephX key file."""
    key = _secret(key_source, "CephX key") if key_source is not None else None
    return rbd_mirroring.create_peer(
        _client(opts, pillar, context, profile),
        pool_name,
        cluster_name,
        client_id,
        mon_host,
        key,
    ).as_dict()


def update_peer(
    opts,
    pillar,
    context,
    pool_name,
    peer_uuid,
    cluster_name=None,
    client_id=None,
    mon_host=None,
    key_source=None,
    clear_key=False,
    profile="default",
):
    """Update a legacy peer, sourcing or explicitly clearing its CephX key."""
    if not isinstance(clear_key, bool):
        raise ConfigurationError("clear_key must be a boolean.")
    if clear_key and key_source is not None:
        raise ConfigurationError("key_source and clear_key are mutually exclusive.")
    key = "" if clear_key else None
    if key_source is not None:
        key = _secret(key_source, "CephX key")
    return rbd_mirroring.update_peer(
        _client(opts, pillar, context, profile),
        pool_name,
        peer_uuid,
        cluster_name,
        client_id,
        mon_host,
        key,
    ).as_dict()
