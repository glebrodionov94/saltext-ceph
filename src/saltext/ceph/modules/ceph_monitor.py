"""Inspect Ceph monitor quorum information through Dashboard."""

from saltext.ceph.utils.ceph import monitor_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_monitor"


def __virtual__():
    return __virtualname__


def status(profile="default"):
    """Return monitor map, status, counters and quorum membership.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_monitor.status
    """
    return salt_adapter.invoke(monitor_api.status, __opts__, __pillar__, __context__, profile)
