"""Inspect orchestrator hardware health through Ceph Dashboard."""

from saltext.ceph.utils.ceph import hardware_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_hardware"


def __virtual__():
    return __virtualname__


def summary(categories=None, hostnames=None, profile="default"):
    """Return hardware health totals, optionally filtered by type and host.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_hardware.summary \\
          categories='["storage","memory"]' hostnames='["node1"]'
    """
    return salt_adapter.invoke(
        hardware_api.summary,
        __opts__,
        __pillar__,
        __context__,
        categories,
        hostnames,
        profile,
    )
