"""Salt-facing composition for current Ceph Dashboard NVMe-oF APIs."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import nvmeof
from saltext.ceph.utils.ceph import nvmeof_gateway
from saltext.ceph.utils.ceph import nvmeof_namespace
from saltext.ceph.utils.ceph import nvmeof_subsystem
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import ConfigurationError

OPERATIONS = {
    **nvmeof_gateway.OPERATIONS,
    **nvmeof_subsystem.OPERATIONS,
    **nvmeof_namespace.OPERATIONS,
}


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def _secret(source, label):
    value = secret_file.read(source).rstrip("\r\n")
    if not value:
        raise ConfigurationError(f"{label} file contains only line separators.")
    return nvmeof.text(value, label, max_length=8192)


def call(opts, pillar, context, operation, *args, profile="default", **kwargs):
    """Invoke one non-secret NVMe-oF operation with a cached profile client."""
    try:
        function = OPERATIONS[operation]
    except KeyError:
        raise ConfigurationError("Unknown or secret-bearing NVMe-oF operation.") from None
    return function(
        _client(opts, pillar, context, profile),
        *args,
        **kwargs,
    ).as_dict()


def subsystem_create(
    opts,
    pillar,
    context,
    nqn,
    max_namespaces=None,
    no_group_append=False,
    serial_number=None,
    dhchap_key_source=None,
    gw_group=None,
    server_address=None,
    network_mask=None,
    port=None,
    secure_listeners=False,
    traddr=None,
    model_name=None,
    profile="default",
):
    """Create a subsystem, reading an optional DHCHAP key from a local file."""
    dhchap_key = _secret(dhchap_key_source, "dhchap_key") if dhchap_key_source is not None else None
    return nvmeof_subsystem.subsystem_create(
        _client(opts, pillar, context, profile),
        nqn,
        max_namespaces,
        no_group_append,
        serial_number,
        dhchap_key,
        gw_group,
        server_address,
        network_mask,
        port,
        secure_listeners,
        traddr,
        model_name,
    ).as_dict()


def subsystem_change_key(
    opts,
    pillar,
    context,
    nqn,
    dhchap_key_source,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
    profile="default",
):
    """Rotate a subsystem DHCHAP key read from a local file."""
    dhchap_key = _secret(dhchap_key_source, "dhchap_key")
    return nvmeof_subsystem.subsystem_change_key(
        _client(opts, pillar, context, profile),
        nqn,
        dhchap_key,
        gw_group,
        server_address,
        traddr,
        confirm,
    ).as_dict()


def host_create(
    opts,
    pillar,
    context,
    nqn,
    host_nqn,
    dhchap_key_source=None,
    dhchap_controller_key_source=None,
    psk_source=None,
    gw_group=None,
    server_address=None,
    traddr=None,
    profile="default",
):
    """Create a host, reading optional DHCHAP and TLS-PSK files."""
    dhchap_key = _secret(dhchap_key_source, "dhchap_key") if dhchap_key_source is not None else None
    controller_key = (
        _secret(dhchap_controller_key_source, "dhchap_controller_key")
        if dhchap_controller_key_source is not None
        else None
    )
    psk = _secret(psk_source, "psk") if psk_source is not None else None
    return nvmeof_subsystem.host_create(
        _client(opts, pillar, context, profile),
        nqn,
        host_nqn,
        dhchap_key,
        controller_key,
        psk,
        gw_group,
        server_address,
        traddr,
    ).as_dict()


def host_change_key(
    opts,
    pillar,
    context,
    nqn,
    host_nqn,
    dhchap_key_source,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
    profile="default",
):
    """Rotate a host DHCHAP key read from a local file."""
    dhchap_key = _secret(dhchap_key_source, "dhchap_key")
    return nvmeof_subsystem.host_change_key(
        _client(opts, pillar, context, profile),
        nqn,
        host_nqn,
        dhchap_key,
        gw_group,
        server_address,
        traddr,
        confirm,
    ).as_dict()


def host_change_controller_key(
    opts,
    pillar,
    context,
    nqn,
    host_nqn,
    dhchap_controller_key_source,
    gw_group=None,
    server_address=None,
    traddr=None,
    confirm=False,
    profile="default",
):
    """Rotate a host controller key read from a local file."""
    controller_key = _secret(
        dhchap_controller_key_source,
        "dhchap_controller_key",
    )
    return nvmeof_subsystem.host_change_controller_key(
        _client(opts, pillar, context, profile),
        nqn,
        host_nqn,
        controller_key,
        gw_group,
        server_address,
        traddr,
        confirm,
    ).as_dict()


SECRET_OPERATIONS = {
    "subsystem_create": subsystem_create,
    "subsystem_change_key": subsystem_change_key,
    "host_create": host_create,
    "host_change_key": host_change_key,
    "host_change_controller_key": host_change_controller_key,
}

PUBLIC_OPERATIONS = {**OPERATIONS, **SECRET_OPERATIONS}
