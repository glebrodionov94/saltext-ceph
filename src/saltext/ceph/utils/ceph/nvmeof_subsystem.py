"""Current public NVMe-oF subsystem, listener, host, and connection APIs."""

from saltext.ceph.utils.ceph import nvmeof
from saltext.ceph.utils.ceph.errors import ConfigurationError

SUBSYSTEM_PATH = f"{nvmeof.BASE_PATH}/subsystem"


def _subsystem_path(nqn, suffix=None):
    path = f"{SUBSYSTEM_PATH}/{nvmeof.encoded(nvmeof.nqn(nqn))}"
    return f"{path}/{suffix}" if suffix else path


def _listener_path(nqn, host_name=None, traddr=None, trsvcid=None):
    path = _subsystem_path(nqn, "listener")
    if host_name is not None:
        path += f"/{nvmeof.encoded(_host_name(host_name, wildcard=True))}"
        path += f"/{nvmeof.encoded(nvmeof.ip_address(traddr))}"
        path += f"/{nvmeof.port(trsvcid, 'trsvcid')}"
    return path


def _host_path(nqn, host_nqn=None, suffix=None):
    path = _subsystem_path(nqn, "host")
    if host_nqn is not None:
        path += f"/{nvmeof.encoded(nvmeof.nqn(host_nqn, 'host_nqn', wildcard=True))}"
    return f"{path}/{suffix}" if suffix else path


def _host_name(value, *, wildcard=False):
    if wildcard and value == "*":
        return value
    return nvmeof.identifier(value, "host_name")


def _secret(value, label):
    return nvmeof.text(value, label, max_length=8192)


def _routing(gw_group=None, server_address=None, traddr=None):
    return nvmeof.routing(gw_group, server_address, traddr)


def subsystem_list(
    client,
    nqn=None,
    serial_number=None,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """List current NVMe-oF subsystems with optional filters."""
    params = _routing(gw_group, server_address, traddr)
    if nqn is not None:
        params["nqn"] = nvmeof.nqn(nqn)
    if serial_number is not None:
        params["serial_number"] = nvmeof.text(serial_number, "serial_number", max_length=64)
    return nvmeof.request(client, "GET", SUBSYSTEM_PATH, params=params)


def subsystem_get(client, nqn, gw_group=None, server_address=None, traddr=None):
    """Return one NVMe-oF subsystem."""
    return nvmeof.request(
        client,
        "GET",
        _subsystem_path(nqn),
        params=_routing(gw_group, server_address, traddr),
    )


def subsystem_create(
    client,
    nqn,
    max_namespaces=None,
    no_group_append=False,
    serial_number=None,
    dhchap_key=None,
    gw_group=None,
    server_address=None,
    network_mask=None,
    port=None,
    secure_listeners=False,
    traddr=None,
    model_name=None,
):
    """Create a subsystem, optionally with auto-listeners and an in-band key."""
    data = {
        "nqn": nvmeof.nqn(nqn),
        "no_group_append": nvmeof.boolean(no_group_append, "no_group_append"),
        "secure_listeners": nvmeof.boolean(secure_listeners, "secure_listeners"),
    }
    if max_namespaces is not None:
        data["max_namespaces"] = nvmeof.integer(max_namespaces, "max_namespaces", minimum=1)
    if serial_number is not None:
        data["serial_number"] = nvmeof.text(serial_number, "serial_number", max_length=64)
    if dhchap_key is not None:
        data["dhchap_key"] = _secret(dhchap_key, "dhchap_key")
    masks = None
    if network_mask is not None:
        masks = nvmeof.string_list(network_mask, "network_mask", optional=False)
        masks = [nvmeof.network(value, "network_mask") for value in masks]
        if len(set(masks)) != len(masks):
            raise ConfigurationError("network_mask must not contain duplicate networks.")
        data["network_mask"] = masks
    if port is not None:
        if masks is None:
            raise ConfigurationError("port requires network_mask.")
        data["port"] = nvmeof.port(port)
    if secure_listeners and masks is None:
        raise ConfigurationError("secure_listeners=True requires network_mask.")
    if model_name is not None:
        data["model_name"] = nvmeof.text(model_name, "model_name", max_length=64)
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "POST", SUBSYSTEM_PATH, data=data)


def subsystem_delete(
    client,
    nqn,
    force=False,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Delete a subsystem after explicit confirmation."""
    nvmeof.confirmed(confirm, "Deleting an NVMe-oF subsystem")
    params = {"force": nvmeof.boolean(force, "force")}
    params.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "DELETE", _subsystem_path(nqn), params=params)


def subsystem_change_key(
    client,
    nqn,
    dhchap_key,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Rotate a subsystem in-band authentication key after confirmation."""
    nvmeof.confirmed(confirm, "Changing an NVMe-oF subsystem authentication key")
    data = {"dhchap_key": _secret(dhchap_key, "dhchap_key")}
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", _subsystem_path(nqn, "change_key"), data=data)


def listener_list(client, nqn, gw_group=None, server_address=None, traddr=None):
    """List listeners for a subsystem."""
    return nvmeof.request(
        client,
        "GET",
        _listener_path(nqn),
        params=_routing(gw_group, server_address, traddr),
    )


def listener_create(
    client,
    nqn,
    host_name,
    traddr,
    trsvcid=None,
    adrfam=0,
    gw_group=None,
    server_address=None,
    secure=False,
    force=False,
    verify_host_name=False,
    confirm=False,
):
    """Create a listener, confirming any forced security override."""
    force = nvmeof.boolean(force, "force")
    if force:
        nvmeof.confirmed(confirm, "Forcing NVMe-oF listener creation")
    else:
        nvmeof.boolean(confirm, "confirm")
    traddr = nvmeof.ip_address(traddr)
    data = {
        "host_name": _host_name(host_name),
        "traddr": traddr,
        "adrfam": nvmeof.address_family(adrfam, traddr),
        "secure": nvmeof.boolean(secure, "secure"),
        "force": force,
        "verify_host_name": nvmeof.boolean(verify_host_name, "verify_host_name"),
    }
    if trsvcid is not None:
        data["trsvcid"] = nvmeof.port(trsvcid, "trsvcid")
    data.update(nvmeof.routing(gw_group, server_address))
    return nvmeof.request(client, "POST", _listener_path(nqn), data=data)


def listener_delete(
    client,
    nqn,
    host_name,
    traddr,
    trsvcid,
    adrfam=0,
    force=False,
    gw_group=None,
    server_address=None,
    confirm=False,
):
    """Delete a listener after explicit confirmation."""
    nvmeof.confirmed(confirm, "Deleting an NVMe-oF listener")
    traddr = nvmeof.ip_address(traddr)
    params = {
        "adrfam": nvmeof.address_family(adrfam, traddr),
        "force": nvmeof.boolean(force, "force"),
    }
    params.update(nvmeof.routing(gw_group, server_address))
    return nvmeof.request(
        client,
        "DELETE",
        _listener_path(nqn, host_name, traddr, trsvcid),
        params=params,
    )


def host_list(client, nqn, gw_group=None, server_address=None, traddr=None):
    """List subsystem host allowlist entries."""
    return nvmeof.request(
        client,
        "GET",
        _host_path(nqn),
        params=_routing(gw_group, server_address, traddr),
    )


def host_create(
    client,
    nqn,
    host_nqn,
    dhchap_key=None,
    dhchap_controller_key=None,
    psk=None,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """Add a host with optional protected authentication material."""
    host_nqn = nvmeof.nqn(host_nqn, "host_nqn", wildcard=True)
    if host_nqn == "*" and any(
        value is not None for value in (dhchap_key, dhchap_controller_key, psk)
    ):
        raise ConfigurationError("Wildcard host access cannot carry authentication keys.")
    data = {"host_nqn": host_nqn}
    for key, value in {
        "dhchap_key": dhchap_key,
        "dhchap_controller_key": dhchap_controller_key,
        "psk": psk,
    }.items():
        if value is not None:
            data[key] = _secret(value, key)
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "POST", _host_path(nqn), data=data)


def host_delete(
    client,
    nqn,
    host_nqn,
    force=False,
    gw_group=None,
    server_address=None,
    traddr=None,
    keep_connections=False,
    confirm=False,
):
    """Remove host access after explicit confirmation."""
    nvmeof.confirmed(confirm, "Deleting an NVMe-oF host allowlist entry")
    params = {
        "force": nvmeof.boolean(force, "force"),
        "keep_connections": nvmeof.boolean(keep_connections, "keep_connections"),
    }
    params.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "DELETE", _host_path(nqn, host_nqn), params=params)


def host_change_key(
    client,
    nqn,
    host_nqn,
    dhchap_key,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Rotate a host DH-HMAC-CHAP key after confirmation."""
    nvmeof.confirmed(confirm, "Changing an NVMe-oF host authentication key")
    data = {"dhchap_key": _secret(dhchap_key, "dhchap_key")}
    data.update(_routing(gw_group, server_address, traddr))
    path = _host_path(nqn, nvmeof.nqn(host_nqn, "host_nqn"), "change_key")
    return nvmeof.request(client, "PUT", path, data=data)


def host_change_controller_key(
    client,
    nqn,
    host_nqn,
    dhchap_controller_key,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Rotate a host controller key after confirmation."""
    nvmeof.confirmed(confirm, "Changing an NVMe-oF host controller key")
    data = {"dhchap_controller_key": _secret(dhchap_controller_key, "dhchap_controller_key")}
    data.update(_routing(gw_group, server_address, traddr))
    path = _host_path(
        nqn,
        nvmeof.nqn(host_nqn, "host_nqn"),
        "change_controller_key",
    )
    return nvmeof.request(client, "PUT", path, data=data)


def host_delete_key(
    client,
    nqn,
    host_nqn,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Delete a host DH-HMAC-CHAP key after confirmation."""
    nvmeof.confirmed(confirm, "Deleting an NVMe-oF host authentication key")
    data = _routing(gw_group, server_address, traddr)
    path = _host_path(nqn, nvmeof.nqn(host_nqn, "host_nqn"), "del_key")
    return nvmeof.request(client, "PUT", path, data=data)


def host_delete_controller_key(
    client,
    nqn,
    host_nqn,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Delete a host controller key after confirmation."""
    nvmeof.confirmed(confirm, "Deleting an NVMe-oF host controller key")
    data = _routing(gw_group, server_address, traddr)
    path = _host_path(
        nqn,
        nvmeof.nqn(host_nqn, "host_nqn"),
        "del_controller_key",
    )
    return nvmeof.request(client, "PUT", path, data=data)


def connection_list(client, nqn, gw_group=None, server_address=None, traddr=None):
    """List active connections for one subsystem."""
    return nvmeof.request(
        client,
        "GET",
        _subsystem_path(nqn, "connection"),
        params=_routing(gw_group, server_address, traddr),
    )


OPERATIONS = {
    "subsystem_list": subsystem_list,
    "subsystem_get": subsystem_get,
    "subsystem_delete": subsystem_delete,
    "listener_list": listener_list,
    "listener_create": listener_create,
    "listener_delete": listener_delete,
    "host_list": host_list,
    "host_delete": host_delete,
    "host_delete_key": host_delete_key,
    "host_delete_controller_key": host_delete_controller_key,
    "connection_list": connection_list,
}

SECRET_OPERATIONS = {
    "subsystem_create": subsystem_create,
    "subsystem_change_key": subsystem_change_key,
    "host_create": host_create,
    "host_change_key": host_change_key,
    "host_change_controller_key": host_change_controller_key,
}
