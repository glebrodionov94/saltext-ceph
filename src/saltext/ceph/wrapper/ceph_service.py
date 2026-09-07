"""Manage cephadm services from the salt-ssh controller."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import service_api

__virtualname__ = "ceph_service"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(
    service_name=None,
    offset=0,
    limit=-1,
    search="",
    sort="+service_name",
    profile="default",
):
    """List cephadm services."""
    return _invoke(
        service_api.list_,
        service_name,
        offset,
        limit,
        search,
        sort,
        profile,
    )


def get(service_name, profile="default"):
    """Return one cephadm service."""
    return _invoke(service_api.get, service_name, profile)


def known_types(profile="default"):
    """Return service types known to Ceph."""
    return _invoke(service_api.known_types, profile)


def daemons(service_name, profile="default"):
    """Return daemons belonging to a service."""
    return _invoke(service_api.daemons, service_name, profile)


def create(service_name, service_spec, profile="default"):
    """Create a cephadm service from a structured ServiceSpec."""
    return _invoke(service_api.create, service_name, service_spec, profile)


def update(service_name, service_spec, profile="default"):
    """Update a cephadm service from a structured ServiceSpec."""
    return _invoke(service_api.update, service_name, service_spec, profile)


def delete(service_name, confirm=False, profile="default"):
    """Remove a cephadm service after explicit confirmation."""
    return _invoke(service_api.delete, service_name, confirm, profile)
