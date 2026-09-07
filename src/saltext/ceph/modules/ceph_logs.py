"""Read recent Ceph cluster and audit log entries through Dashboard."""

from saltext.ceph.utils.ceph import logs_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_logs"
__func_alias__ = {"all_": "all"}


def __virtual__():
    return __virtualname__


def all_(profile="default"):
    """Return Dashboard's in-memory cluster and audit log buffers.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_logs.all
    """
    return salt_adapter.invoke(logs_api.all_, __opts__, __pillar__, __context__, profile)
