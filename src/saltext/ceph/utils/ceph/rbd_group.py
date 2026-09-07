"""Current-Ceph RBD group operations from the public ``rbd.py`` controller."""

from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import ConfigurationError

API_VERSION = "1.0"
POOL_PATH = "/api/block/pool"


def _name(value, label):
    return validation.identifier(value, label)


def _confirmed(value, action):
    if not isinstance(value, bool):
        raise ConfigurationError("confirm must be a boolean.")
    if not value:
        raise ConfigurationError(f"{action} requires confirm=True.")


def _integer(value, label, *, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{label} must be an integer.")
    if value < 0 or (value == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ConfigurationError(f"{label} must be a {qualifier} integer.")
    return value


def _namespace_params(namespace):
    if namespace is None:
        return {}
    return {"namespace": _name(namespace, "namespace")}


def _path(pool_name, group_name=None, suffix=None):
    path = f"{POOL_PATH}/{quote(_name(pool_name, 'pool_name'), safe='')}/group"
    if group_name is not None:
        path = f"{path}/{quote(_name(group_name, 'group_name'), safe='')}"
    return f"{path}/{suffix}" if suffix else path


def _snapshot_path(pool_name, group_name, snapshot_name=None, suffix=None):
    path = _path(pool_name, group_name, "snap")
    if snapshot_name is not None:
        path = f"{path}/{quote(_name(snapshot_name, 'snapshot_name'), safe='')}"
    return f"{path}/{suffix}" if suffix else path


def list_(client, pool_name, namespace=None):
    """List RBD groups and their image counts."""
    response = client.request(
        "GET",
        _path(pool_name),
        api_version=API_VERSION,
        params=_namespace_params(namespace),
    )
    return validation.mapping_list_response(response, "Ceph RBD group list")


def get(client, pool_name, group_name, namespace=None):
    """Return group member images."""
    response = client.request(
        "GET",
        _path(pool_name, group_name),
        api_version=API_VERSION,
        params=_namespace_params(namespace),
    )
    return validation.mapping_list_response(response, "Ceph RBD group")


def create(client, pool_name, name, namespace=None):
    """Create an RBD group."""
    data = {"name": _name(name, "name")}
    data.update(_namespace_params(namespace))
    return client.request("POST", _path(pool_name), api_version=API_VERSION, data=data)


def update(client, pool_name, group_name, new_name, namespace=None):
    """Rename an RBD group."""
    group_name = _name(group_name, "group_name")
    new_name = _name(new_name, "new_name")
    if new_name == group_name:
        raise ConfigurationError("new_name must differ from group_name.")
    data = {"new_name": new_name}
    data.update(_namespace_params(namespace))
    return client.request("PUT", _path(pool_name, group_name), api_version=API_VERSION, data=data)


def delete(client, pool_name, group_name, namespace=None, confirm=False):
    """Delete an empty RBD group after confirmation."""
    _confirmed(confirm, "Deleting an RBD group")
    return client.request(
        "DELETE",
        _path(pool_name, group_name),
        api_version=API_VERSION,
        params=_namespace_params(namespace),
    )


def add_image(client, pool_name, group_name, image_name, namespace=None):
    """Add an image from the same pool and namespace to a group."""
    data = {"image_name": _name(image_name, "image_name")}
    data.update(_namespace_params(namespace))
    return client.request(
        "POST",
        _path(pool_name, group_name, "image"),
        api_version=API_VERSION,
        data=data,
    )


def remove_image(client, pool_name, group_name, image_name, namespace=None, confirm=False):
    """Remove an image from a group without deleting it."""
    _confirmed(confirm, "Removing an image from an RBD group")
    params = {"image_name": _name(image_name, "image_name")}
    params.update(_namespace_params(namespace))
    return client.request(
        "DELETE",
        _path(pool_name, group_name, "image"),
        api_version=API_VERSION,
        params=params,
    )


def snapshot_list(client, pool_name, group_name, namespace=None):
    """List crash-consistent group snapshots."""
    response = client.request(
        "GET",
        _snapshot_path(pool_name, group_name),
        api_version=API_VERSION,
        params=_namespace_params(namespace),
    )
    return validation.mapping_list_response(response, "Ceph RBD group snapshot list")


def snapshot_get(client, pool_name, group_name, snapshot_name, namespace=None):
    """Return one group snapshot."""
    response = client.request(
        "GET",
        _snapshot_path(pool_name, group_name, snapshot_name),
        api_version=API_VERSION,
        params=_namespace_params(namespace),
    )
    return validation.mapping_response(response, "Ceph RBD group snapshot")


def snapshot_create(client, pool_name, group_name, snapshot_name, namespace=None, flags=0):
    """Create a crash-consistent group snapshot."""
    flags = _integer(flags, "flags", allow_zero=True)
    data = {"snapshot_name": _name(snapshot_name, "snapshot_name"), "flags": flags}
    data.update(_namespace_params(namespace))
    return client.request(
        "POST",
        _snapshot_path(pool_name, group_name),
        api_version=API_VERSION,
        data=data,
    )


def snapshot_update(
    client,
    pool_name,
    group_name,
    snapshot_name,
    new_snapshot_name,
    namespace=None,
):
    """Rename a group snapshot."""
    snapshot_name = _name(snapshot_name, "snapshot_name")
    new_snapshot_name = _name(new_snapshot_name, "new_snapshot_name")
    if snapshot_name == new_snapshot_name:
        raise ConfigurationError("new_snapshot_name must differ from snapshot_name.")
    data = {"new_snap_name": new_snapshot_name}
    data.update(_namespace_params(namespace))
    return client.request(
        "PUT",
        _snapshot_path(pool_name, group_name, snapshot_name),
        api_version=API_VERSION,
        data=data,
    )


def snapshot_delete(client, pool_name, group_name, snapshot_name, namespace=None, confirm=False):
    """Delete a group snapshot after confirmation."""
    _confirmed(confirm, "Deleting an RBD group snapshot")
    return client.request(
        "DELETE",
        _snapshot_path(pool_name, group_name, snapshot_name),
        api_version=API_VERSION,
        params=_namespace_params(namespace),
    )


def snapshot_rollback(client, pool_name, group_name, snapshot_name, namespace=None, confirm=False):
    """Roll all group images back to a snapshot after confirmation."""
    _confirmed(confirm, "Rolling back an RBD group snapshot")
    return client.request(
        "POST",
        _snapshot_path(pool_name, group_name, snapshot_name, "rollback"),
        api_version=API_VERSION,
        data=_namespace_params(namespace),
    )
