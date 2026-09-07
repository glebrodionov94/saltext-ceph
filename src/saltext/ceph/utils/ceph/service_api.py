"""Salt-facing composition for orchestrator service operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import service


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(
    opts,
    pillar,
    context,
    service_name=None,
    offset=0,
    limit=-1,
    search="",
    sort="+service_name",
    profile="default",
):
    """List orchestrator services."""
    return service.list_(
        _client(opts, pillar, context, profile),
        service_name,
        offset,
        limit,
        search,
        sort,
    ).as_dict()


def get(opts, pillar, context, service_name, profile="default"):
    """Return one orchestrator service."""
    return service.get(_client(opts, pillar, context, profile), service_name).as_dict()


def known_types(opts, pillar, context, profile="default"):
    """Return service types known to Ceph."""
    return service.known_types(_client(opts, pillar, context, profile)).as_dict()


def daemons(opts, pillar, context, service_name, profile="default"):
    """Return daemons belonging to a service."""
    return service.daemons(_client(opts, pillar, context, profile), service_name).as_dict()


def create(opts, pillar, context, service_name, service_spec, profile="default"):
    """Create an orchestrator service."""
    return service.create(
        _client(opts, pillar, context, profile), service_name, service_spec
    ).as_dict()


def update(opts, pillar, context, service_name, service_spec, profile="default"):
    """Update an orchestrator service."""
    return service.update(
        _client(opts, pillar, context, profile), service_name, service_spec
    ).as_dict()


def delete(opts, pillar, context, service_name, confirm=False, profile="default"):
    """Remove an orchestrator service after explicit confirmation."""
    return service.delete(_client(opts, pillar, context, profile), service_name, confirm).as_dict()
