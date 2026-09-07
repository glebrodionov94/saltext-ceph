"""Salt-facing composition for host controller operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import host


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(
    opts,
    pillar,
    context,
    sources=None,
    facts=False,
    offset=0,
    limit=-1,
    search="",
    sort="+hostname",
    include_service_instances=True,
    profile="default",
):
    """List hosts."""
    return host.list_(
        _client(opts, pillar, context, profile),
        sources,
        facts,
        offset,
        limit,
        search,
        sort,
        include_service_instances,
    ).as_dict()


def get(opts, pillar, context, hostname, profile="default"):
    """Return one host."""
    return host.get(_client(opts, pillar, context, profile), hostname).as_dict()


def create(
    opts,
    pillar,
    context,
    hostname,
    address=None,
    labels=None,
    maintenance=False,
    profile="default",
):
    """Add a host to the orchestrator."""
    return host.create(
        _client(opts, pillar, context, profile),
        hostname,
        address,
        labels,
        maintenance,
    ).as_dict()


def delete(opts, pillar, context, hostname, confirm=False, profile="default"):
    """Remove a host from the orchestrator after confirmation."""
    return host.delete(_client(opts, pillar, context, profile), hostname, confirm).as_dict()


def set_labels(opts, pillar, context, hostname, labels, profile="default"):
    """Replace all labels on a host."""
    return host.set_labels(_client(opts, pillar, context, profile), hostname, labels).as_dict()


def toggle_maintenance(opts, pillar, context, hostname, force=False, profile="default"):
    """Toggle maintenance mode on a host."""
    return host.toggle_maintenance(
        _client(opts, pillar, context, profile), hostname, force
    ).as_dict()


def drain(opts, pillar, context, hostname, profile="default"):
    """Drain orchestrated daemons from a host."""
    return host.drain(_client(opts, pillar, context, profile), hostname).as_dict()


def devices(opts, pillar, context, hostname, profile="default"):
    """Return devices associated with a host."""
    return host.devices(_client(opts, pillar, context, profile), hostname).as_dict()


def smart(opts, pillar, context, hostname, profile="default"):
    """Return host SMART data."""
    return host.smart(_client(opts, pillar, context, profile), hostname).as_dict()


def inventory(opts, pillar, context, hostname, refresh=False, profile="default"):
    """Return host device inventory."""
    return host.inventory(_client(opts, pillar, context, profile), hostname, refresh).as_dict()


def identify_device(opts, pillar, context, hostname, device, duration=10, profile="default"):
    """Blink a host device identification LED."""
    return host.identify_device(
        _client(opts, pillar, context, profile), hostname, device, duration
    ).as_dict()


def daemons(opts, pillar, context, hostname, profile="default"):
    """Return orchestrated daemons on a host."""
    return host.daemons(_client(opts, pillar, context, profile), hostname).as_dict()
