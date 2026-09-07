"""Current public Ceph Dashboard NVMe-oF gateway and SPDK operations."""

from saltext.ceph.utils.ceph import nvmeof
from saltext.ceph.utils.ceph.errors import ConfigurationError

GATEWAY_PATH = f"{nvmeof.BASE_PATH}/gateway"
SPDK_PATH = f"{nvmeof.BASE_PATH}/spdk"

GATEWAY_LOG_LEVELS = frozenset(("critical", "debug", "error", "info", "warning"))
SPDK_LOG_LEVELS = frozenset(("DEBUG", "ERROR", "INFO", "NOTICE", "WARNING"))


def _routing(gw_group=None, server_address=None, traddr=None, *, require_address=False):
    return nvmeof.routing(gw_group, server_address, traddr, require_address=require_address)


def gateway_info(client, gw_group=None, server_address=None, traddr=None):
    """Return gateway information."""
    return nvmeof.request(
        client,
        "GET",
        GATEWAY_PATH,
        params=_routing(gw_group, server_address, traddr),
    )


def gateway_groups(client):
    """Return orchestrator NVMe-oF gateway groups."""
    return nvmeof.request(client, "GET", f"{GATEWAY_PATH}/group")


def gateway_version(client, gw_group=None, server_address=None, traddr=None):
    """Return a gateway version."""
    return nvmeof.request(
        client,
        "GET",
        f"{GATEWAY_PATH}/version",
        params=_routing(gw_group, server_address, traddr),
    )


def gateway_log_level(client, gw_group=None, server_address=None, traddr=None):
    """Return a gateway log level."""
    return nvmeof.request(
        client,
        "GET",
        f"{GATEWAY_PATH}/log_level",
        params=_routing(gw_group, server_address, traddr),
    )


def gateway_set_log_level(
    client,
    log_level,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """Set a gateway log level."""
    if not isinstance(log_level, str) or log_level.strip().lower() not in GATEWAY_LOG_LEVELS:
        raise ConfigurationError(
            f"log_level must be one of: {', '.join(sorted(GATEWAY_LOG_LEVELS))}."
        )
    data = {"log_level": log_level.strip().lower()}
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", f"{GATEWAY_PATH}/log_level", data=data)


def gateway_stats(client, gw_group=None, server_address=None, traddr=None):
    """Return gateway IO statistics."""
    return nvmeof.request(
        client,
        "GET",
        f"{GATEWAY_PATH}/stats",
        params=_routing(gw_group, server_address, traddr),
    )


def gateway_listener_info(
    client,
    nqn,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """Return gateway listener state for a subsystem."""
    path = f"{GATEWAY_PATH}/listener_info/{nvmeof.encoded(nvmeof.nqn(nqn))}"
    return nvmeof.request(
        client,
        "GET",
        path,
        params=_routing(gw_group, server_address, traddr),
    )


def gateway_set_io_stats(
    client,
    enabled,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """Enable or disable gateway IO statistics collection."""
    data = {"enabled": nvmeof.boolean(enabled, "enabled")}
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", f"{GATEWAY_PATH}/io_stats", data=data)


def gateway_thread_stats(client, gw_group=None, server_address=None, traddr=None):
    """Return SPDK thread statistics through the gateway controller."""
    return nvmeof.request(
        client,
        "GET",
        f"{GATEWAY_PATH}/thread_stats",
        params=_routing(gw_group, server_address, traddr),
    )


def gateway_refresh_network(
    client,
    nqn="",
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
):
    """Refresh auto-listeners after explicit confirmation."""
    nvmeof.confirmed(confirm, "Refreshing NVMe-oF gateway network listeners")
    if nqn:
        nqn = nvmeof.nqn(nqn)
    elif not isinstance(nqn, str):
        raise ConfigurationError("nqn must be a string.")
    data = {"nqn": nqn}
    data.update(_routing(gw_group, server_address, traddr, require_address=True))
    return nvmeof.request(client, "PUT", f"{GATEWAY_PATH}/refresh_network", data=data)


def spdk_log_level(
    client,
    all_log_flags=None,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """Return SPDK log levels and flags."""
    params = _routing(gw_group, server_address, traddr)
    if all_log_flags is not None:
        params["all_log_flags"] = nvmeof.boolean(all_log_flags, "all_log_flags")
    return nvmeof.request(client, "GET", f"{SPDK_PATH}/log_level", params=params)


def _spdk_level(value, label):
    if value is None:
        return None
    if not isinstance(value, str) or value.strip().upper() not in SPDK_LOG_LEVELS:
        raise ConfigurationError(f"{label} must be one of: {', '.join(sorted(SPDK_LOG_LEVELS))}.")
    return value.strip().upper()


def _log_flags(values):
    values = nvmeof.string_list(values, "extra_log_flags")
    if values is None:
        return None
    return [nvmeof.identifier(value, "extra_log_flags") for value in values]


def spdk_set_log_level(
    client,
    log_level=None,
    print_level=None,
    extra_log_flags=None,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """Set one or more SPDK log settings."""
    log_level = _spdk_level(log_level, "log_level")
    print_level = _spdk_level(print_level, "print_level")
    extra_log_flags = _log_flags(extra_log_flags)
    if log_level is None and print_level is None and extra_log_flags is None:
        raise ConfigurationError("At least one SPDK log setting must be provided.")
    data = {
        key: value
        for key, value in {
            "log_level": log_level,
            "print_level": print_level,
            "extra_log_flags": extra_log_flags,
        }.items()
        if value is not None
    }
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", f"{SPDK_PATH}/log_level", data=data)


def spdk_disable_log_level(
    client,
    extra_log_flags=None,
    gw_group=None,
    server_address=None,
    traddr=None,
):
    """Disable selected or default SPDK log flags."""
    data = {}
    extra_log_flags = _log_flags(extra_log_flags)
    if extra_log_flags is not None:
        data["extra_log_flags"] = extra_log_flags
    data.update(_routing(gw_group, server_address, traddr))
    return nvmeof.request(client, "PUT", f"{SPDK_PATH}/log_level/disable", data=data)


OPERATIONS = {
    "gateway_info": gateway_info,
    "gateway_groups": gateway_groups,
    "gateway_version": gateway_version,
    "gateway_log_level": gateway_log_level,
    "gateway_set_log_level": gateway_set_log_level,
    "gateway_stats": gateway_stats,
    "gateway_listener_info": gateway_listener_info,
    "gateway_set_io_stats": gateway_set_io_stats,
    "gateway_thread_stats": gateway_thread_stats,
    "gateway_refresh_network": gateway_refresh_network,
    "spdk_log_level": spdk_log_level,
    "spdk_set_log_level": spdk_set_log_level,
    "spdk_disable_log_level": spdk_disable_log_level,
}
