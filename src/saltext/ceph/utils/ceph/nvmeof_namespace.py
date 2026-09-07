"""Current public Ceph Dashboard NVMe-oF namespace operations."""

from saltext.ceph.utils.ceph import nvmeof
from saltext.ceph.utils.ceph.errors import ConfigurationError

NAMESPACE_PATH = f"{nvmeof.BASE_PATH}/subsystem"
MAX_QOS_VALUE = (1 << 63) - 1
BLOCK_SIZES = frozenset((512, 4096))
ENCRYPTION_FORMATS = frozenset(("LUKS1", "LUKS2"))


def _collection_path(nqn, suffix=None):
    path = f"{NAMESPACE_PATH}/{nvmeof.encoded(nvmeof.nqn(nqn))}/namespace"
    return f"{path}/{suffix}" if suffix else path


def _member_path(nqn, nsid, suffix=None):
    path = f"{_collection_path(nqn)}/{nvmeof.encoded(nvmeof.namespace_id(nsid))}"
    return f"{path}/{suffix}" if suffix else path


def _routing(gw_group=None, server_address=None, traddr=None):
    return nvmeof.routing(gw_group, server_address, traddr)


def _optional_identifier(value, label):
    return nvmeof.identifier(value, label) if value is not None else None


def _optional_size(value, label):
    if value is None:
        return None
    return nvmeof.integer(value, label, minimum=1, maximum=MAX_QOS_VALUE)


def _optional_qos(value, label):
    if value is None:
        return None
    return nvmeof.integer(value, label, maximum=MAX_QOS_VALUE)


def _filters(nsid=None, uuid=None):
    result = {}
    if nsid is not None:
        result["nsid"] = nvmeof.namespace_id(nsid)
    if uuid is not None:
        result["uuid"] = nvmeof.uuid_value(uuid)
    return result


def _force_confirmation(force, confirm, action):
    force = nvmeof.boolean(force, "force")
    if force:
        nvmeof.confirmed(confirm, action)
    else:
        nvmeof.boolean(confirm, "confirm")
    return force


def namespace_list(
    client,
    nqn,
    nsid=None,
    uuid=None,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """List namespaces in one subsystem with optional ID or UUID filters."""
    params = _filters(nsid, uuid)
    params.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "GET", _collection_path(nqn), params=params)


def namespace_get(client, nqn, nsid, gw_group=None, server_address=None, traddr=None):
    """Return one namespace."""
    return nvmeof.request(
        client,
        "GET",
        _member_path(nqn, nsid),
        params=_routing(gw_group, server_address, traddr),
    )


def namespace_io_stats(client, nqn, nsid, gw_group=None, server_address=None, traddr=None):
    """Return IO statistics for one namespace."""
    return nvmeof.request(
        client,
        "GET",
        _member_path(nqn, nsid, "io_stats"),
        params=_routing(gw_group, server_address, traddr),
    )


def namespace_create(
    client,
    nqn,
    rbd_image_name,
    rbd_pool="rbd",
    rbd_data_pool=None,
    nsid=None,
    uuid=None,
    create_image=False,
    size=None,
    rbd_image_size=None,
    trash_image=False,
    block_size=512,
    load_balancing_group=None,
    force=False,
    no_auto_visible=False,
    disable_auto_resize=False,
    read_only=False,
    location=None,
    gw_group=None,
    server_address=None,
    traddr=None,
    rados_namespace=None,
    encryption_format=None,
    encryption_algorithm=None,
    key_id=None,
    confirm=False,
):
    """Create a namespace using the current Dashboard request schema."""
    if size is not None and rbd_image_size is not None:
        raise ConfigurationError("size and rbd_image_size are mutually exclusive.")
    force = _force_confirmation(
        force,
        confirm,
        "Forcing creation of an NVMe-oF namespace",
    )
    block_size = nvmeof.integer(block_size, "block_size", minimum=1)
    if block_size not in BLOCK_SIZES:
        raise ConfigurationError("block_size must be 512 or 4096 bytes.")

    formats = nvmeof.string_list(
        encryption_format,
        "encryption_format",
        allowed=ENCRYPTION_FORMATS,
    )
    key_ids = nvmeof.string_list(key_id, "key_id")
    if formats is None:
        formats = []
    if key_ids is None:
        key_ids = []
    formats = [value.strip().lower() for value in formats]
    key_ids = [value.strip() for value in key_ids]
    if any(not value for value in key_ids):
        raise ConfigurationError("key_id values must not be blank.")
    if len(set(formats)) != len(formats) or len(set(key_ids)) != len(key_ids):
        raise ConfigurationError("Encryption formats and key IDs must not contain duplicates.")
    if len(formats) != len(key_ids):
        raise ConfigurationError("The number of key_id values must match encryption_format values.")
    algorithm = None
    if encryption_algorithm is not None:
        algorithm = nvmeof.text(
            encryption_algorithm,
            "encryption_algorithm",
            max_length=64,
        ).strip()
        if not algorithm:
            raise ConfigurationError("encryption_algorithm must not be blank.")
        algorithm = algorithm.lower()

    data = {
        "rbd_image_name": nvmeof.identifier(rbd_image_name, "rbd_image_name"),
        "rbd_pool": nvmeof.identifier(rbd_pool, "rbd_pool"),
        "create_image": nvmeof.boolean(create_image, "create_image"),
        "trash_image": nvmeof.boolean(trash_image, "trash_image"),
        "block_size": block_size,
        "force": force,
        "no_auto_visible": nvmeof.boolean(no_auto_visible, "no_auto_visible"),
        "disable_auto_resize": nvmeof.boolean(disable_auto_resize, "disable_auto_resize"),
        "read_only": nvmeof.boolean(read_only, "read_only"),
    }
    optional = {
        "rbd_data_pool": _optional_identifier(rbd_data_pool, "rbd_data_pool"),
        "nsid": nvmeof.namespace_id(nsid, optional=True),
        "uuid": nvmeof.uuid_value(uuid, optional=True),
        "size": _optional_size(size, "size"),
        "rbd_image_size": _optional_size(rbd_image_size, "rbd_image_size"),
        "load_balancing_group": (
            nvmeof.integer(load_balancing_group, "load_balancing_group", minimum=1)
            if load_balancing_group is not None
            else None
        ),
        "location": (
            nvmeof.text(location, "location", allow_empty=True, max_length=255)
            if location is not None
            else None
        ),
        "rados_namespace": _optional_identifier(rados_namespace, "rados_namespace"),
        "encryption_format": formats or None,
        "encryption_algorithm": algorithm,
        "key_id": key_ids or None,
    }
    data.update({key: value for key, value in optional.items() if value is not None})
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "POST", _collection_path(nqn), data=data)


def namespace_set_qos(
    client,
    nqn,
    nsid,
    rw_ios_per_second=None,
    rw_mbytes_per_second=None,
    r_mbytes_per_second=None,
    w_mbytes_per_second=None,
    force=False,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Set namespace QoS limits."""
    values = {
        "rw_ios_per_second": _optional_qos(rw_ios_per_second, "rw_ios_per_second"),
        "rw_mbytes_per_second": _optional_qos(rw_mbytes_per_second, "rw_mbytes_per_second"),
        "r_mbytes_per_second": _optional_qos(r_mbytes_per_second, "r_mbytes_per_second"),
        "w_mbytes_per_second": _optional_qos(w_mbytes_per_second, "w_mbytes_per_second"),
    }
    if all(value is None for value in values.values()):
        raise ConfigurationError("At least one namespace QoS limit must be provided.")
    data = {key: value for key, value in values.items() if value is not None}
    data["force"] = _force_confirmation(
        force,
        confirm,
        "Forcing an NVMe-oF namespace QoS change",
    )
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", _member_path(nqn, nsid, "set_qos"), data=data)


def namespace_change_load_balancing_group(
    client,
    nqn,
    nsid,
    load_balancing_group,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Pin a namespace to a load-balancing group."""
    nvmeof.confirmed(confirm, "Changing an NVMe-oF namespace load-balancing group")
    data = {
        "load_balancing_group": nvmeof.integer(
            load_balancing_group, "load_balancing_group", minimum=1
        )
    }
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(
        client,
        "PUT",
        _member_path(nqn, nsid, "change_load_balancing_group"),
        data=data,
    )


def namespace_resize(
    client,
    nqn,
    nsid,
    rbd_image_size,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Resize a namespace's RBD image after explicit confirmation."""
    nvmeof.confirmed(confirm, "Resizing an NVMe-oF namespace")
    data = {"rbd_image_size": _optional_size(rbd_image_size, "rbd_image_size")}
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", _member_path(nqn, nsid, "resize"), data=data)


def namespace_add_host(
    client,
    nqn,
    nsid,
    host_nqn,
    force=None,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Grant a host access to a namespace."""
    data = {"host_nqn": nvmeof.nqn(host_nqn, "host_nqn", wildcard=True)}
    if force is not None:
        data["force"] = _force_confirmation(
            force,
            confirm,
            "Forcing an NVMe-oF namespace host grant",
        )
    else:
        nvmeof.boolean(confirm, "confirm")
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", _member_path(nqn, nsid, "add_host"), data=data)


def namespace_delete_host(
    client,
    nqn,
    nsid,
    host_nqn,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Revoke a host's namespace access after confirmation."""
    nvmeof.confirmed(confirm, "Deleting an NVMe-oF namespace host grant")
    data = {"host_nqn": nvmeof.nqn(host_nqn, "host_nqn", wildcard=True)}
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", _member_path(nqn, nsid, "del_host"), data=data)


def namespace_change_visibility(
    client,
    nqn,
    nsid,
    auto_visible,
    force=False,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Change namespace visibility after explicit confirmation."""
    nvmeof.confirmed(confirm, "Changing NVMe-oF namespace visibility")
    data = {
        "auto_visible": nvmeof.boolean(auto_visible, "auto_visible"),
        "force": nvmeof.boolean(force, "force"),
    }
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(
        client,
        "PUT",
        _member_path(nqn, nsid, "change_visibility"),
        data=data,
    )


def namespace_change_location(
    client,
    nqn,
    nsid,
    location,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Set or clear a namespace location after confirmation."""
    nvmeof.confirmed(confirm, "Changing an NVMe-oF namespace location")
    data = {"location": nvmeof.text(location, "location", allow_empty=True, max_length=255)}
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(
        client,
        "PUT",
        _member_path(nqn, nsid, "change_location"),
        data=data,
    )


def namespace_list_hosts(
    client,
    nqn,
    nsid=None,
    uuid=None,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """List namespaces and their allowed hosts."""
    params = _filters(nsid, uuid)
    params.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "GET", _collection_path(nqn, "list_hosts"), params=params)


def namespace_list_locations(
    client,
    nqn,
    nsid=None,
    uuid=None,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """List aggregated namespace locations."""
    params = _filters(nsid, uuid)
    params.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(
        client,
        "GET",
        _collection_path(nqn, "list_locations"),
        params=params,
    )


def namespace_set_auto_resize(
    client,
    nqn,
    nsid,
    auto_resize_enabled,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """Enable or disable automatic namespace resizing."""
    data = {"auto_resize_enabled": nvmeof.boolean(auto_resize_enabled, "auto_resize_enabled")}
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(
        client,
        "PUT",
        _member_path(nqn, nsid, "set_auto_resize"),
        data=data,
    )


def namespace_set_rbd_trash_image(
    client,
    nqn,
    nsid,
    rbd_trash_image_on_delete,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Change whether namespace deletion moves its RBD image to trash."""
    nvmeof.confirmed(confirm, "Changing NVMe-oF namespace RBD trash behavior")
    data = {
        "rbd_trash_image_on_delete": nvmeof.boolean(
            rbd_trash_image_on_delete, "rbd_trash_image_on_delete"
        )
    }
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(
        client,
        "PUT",
        _member_path(nqn, nsid, "set_rbd_trash_image"),
        data=data,
    )


def namespace_refresh_size(
    client,
    nqn,
    nsid,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Refresh namespace size from RBD after explicit confirmation."""
    nvmeof.confirmed(confirm, "Refreshing an NVMe-oF namespace size")
    data = _routing(gw_group, server_address, traddr)
    return nvmeof.request(
        client,
        "PUT",
        _member_path(nqn, nsid, "refresh_size"),
        data=data,
    )


def namespace_unpin(
    client,
    nqn,
    nsid,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Unpin a namespace load-balancing group after confirmation."""
    nvmeof.confirmed(confirm, "Unpinning an NVMe-oF namespace")
    data = _routing(gw_group, server_address, traddr)
    return nvmeof.request(client, "PUT", _member_path(nqn, nsid, "unpin"), data=data)


def namespace_update(
    client,
    nqn,
    nsid,
    rbd_image_size=None,
    load_balancing_group=None,
    rw_ios_per_second=None,
    rw_mbytes_per_second=None,
    r_mbytes_per_second=None,
    w_mbytes_per_second=None,
    trash_image=None,
    location=None,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Apply the current controller's compound namespace update."""
    values = {
        "rbd_image_size": _optional_size(rbd_image_size, "rbd_image_size"),
        "load_balancing_group": (
            nvmeof.integer(load_balancing_group, "load_balancing_group", minimum=1)
            if load_balancing_group is not None
            else None
        ),
        "rw_ios_per_second": _optional_qos(rw_ios_per_second, "rw_ios_per_second"),
        "rw_mbytes_per_second": _optional_qos(rw_mbytes_per_second, "rw_mbytes_per_second"),
        "r_mbytes_per_second": _optional_qos(r_mbytes_per_second, "r_mbytes_per_second"),
        "w_mbytes_per_second": _optional_qos(w_mbytes_per_second, "w_mbytes_per_second"),
        "trash_image": (
            nvmeof.boolean(trash_image, "trash_image") if trash_image is not None else None
        ),
        "location": (
            nvmeof.text(location, "location", allow_empty=True, max_length=255)
            if location is not None
            else None
        ),
    }
    data = {key: value for key, value in values.items() if value is not None}
    if not data:
        raise ConfigurationError("At least one namespace update field must be provided.")
    nvmeof.confirmed(confirm, "Updating an NVMe-oF namespace")
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PATCH", _member_path(nqn, nsid), data=data)


def namespace_delete(
    client,
    nqn,
    nsid,
    force=False,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Delete a namespace after explicit confirmation."""
    nvmeof.confirmed(confirm, "Deleting an NVMe-oF namespace")
    params = {"force": nvmeof.boolean(force, "force")}
    params.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "DELETE", _member_path(nqn, nsid), params=params)


OPERATIONS = {
    "namespace_list": namespace_list,
    "namespace_get": namespace_get,
    "namespace_io_stats": namespace_io_stats,
    "namespace_create": namespace_create,
    "namespace_set_qos": namespace_set_qos,
    "namespace_change_load_balancing_group": namespace_change_load_balancing_group,
    "namespace_resize": namespace_resize,
    "namespace_add_host": namespace_add_host,
    "namespace_delete_host": namespace_delete_host,
    "namespace_change_visibility": namespace_change_visibility,
    "namespace_change_location": namespace_change_location,
    "namespace_list_hosts": namespace_list_hosts,
    "namespace_list_locations": namespace_list_locations,
    "namespace_set_auto_resize": namespace_set_auto_resize,
    "namespace_set_rbd_trash_image": namespace_set_rbd_trash_image,
    "namespace_refresh_size": namespace_refresh_size,
    "namespace_unpin": namespace_unpin,
    "namespace_update": namespace_update,
    "namespace_delete": namespace_delete,
}
