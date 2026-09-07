"""Inspect Ceph monitor quorum information from salt-ssh."""

from saltext.ceph.utils.ceph import monitor_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_monitor"


def __virtual__():
    return __virtualname__


def status(profile="default"):
    """Return monitor map, status, counters and quorum membership."""
    return salt_adapter.invoke(monitor_api.status, __opts__, {}, __context__, profile)
