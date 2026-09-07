"""Read recent Ceph cluster and audit log entries from salt-ssh."""

from saltext.ceph.utils.ceph import logs_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_logs"
__func_alias__ = {"all_": "all"}


def __virtual__():
    return __virtualname__


def all_(profile="default"):
    """Return Dashboard's in-memory cluster and audit log buffers."""
    return salt_adapter.invoke(logs_api.all_, __opts__, {}, __context__, profile)
