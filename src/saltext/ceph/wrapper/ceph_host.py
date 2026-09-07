"""Manage cephadm hosts from salt-ssh."""

from saltext.ceph.utils.ceph import host_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_host"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(
    sources=None,
    facts=False,
    offset=0,
    limit=-1,
    search="",
    sort="+hostname",
    include_service_instances=True,
    profile="default",
):
    """List hosts, returning every host by default."""
    return _invoke(
        host_api.list_,
        sources,
        facts,
        offset,
        limit,
        search,
        sort,
        include_service_instances,
        profile,
    )


def get(hostname, profile="default"):
    """Return one host."""
    return _invoke(host_api.get, hostname, profile)


def create(hostname, address=None, labels=None, maintenance=False, profile="default"):
    """Add a host to the orchestrator."""
    return _invoke(host_api.create, hostname, address, labels, maintenance, profile)


def delete(hostname, confirm=False, profile="default"):
    """Remove a host from the orchestrator after explicit confirmation."""
    return _invoke(host_api.delete, hostname, confirm, profile)


def set_labels(hostname, labels, profile="default"):
    """Replace all orchestrator labels on a host."""
    return _invoke(host_api.set_labels, hostname, labels, profile)


def toggle_maintenance(hostname, force=False, profile="default"):
    """Toggle host maintenance mode."""
    return _invoke(host_api.toggle_maintenance, hostname, force, profile)


def drain(hostname, profile="default"):
    """Schedule removal of orchestrated daemons from a host."""
    return _invoke(host_api.drain, hostname, profile)


def devices(hostname, profile="default"):
    """Return Ceph devices associated with a host."""
    return _invoke(host_api.devices, hostname, profile)


def smart(hostname, profile="default"):
    """Return SMART data for a host."""
    return _invoke(host_api.smart, hostname, profile)


def inventory(hostname, refresh=False, profile="default"):
    """Return orchestrator device inventory for one host."""
    return _invoke(host_api.inventory, hostname, refresh, profile)


def identify_device(hostname, device, duration=10, profile="default"):
    """Blink a host device identification LED."""
    return _invoke(host_api.identify_device, hostname, device, duration, profile)


def daemons(hostname, profile="default"):
    """Return orchestrated daemons placed on a host."""
    return _invoke(host_api.daemons, hostname, profile)
