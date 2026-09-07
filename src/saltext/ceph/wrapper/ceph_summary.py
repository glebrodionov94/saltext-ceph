"""Read the Ceph Dashboard aggregate summary from salt-ssh."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import summary_api

__virtualname__ = "ceph_summary"


def __virtual__():
    return __virtualname__


def get(profile="default"):
    """Return cluster health, manager identity, tasks and mirroring counts."""
    return salt_adapter.invoke(summary_api.get, __opts__, {}, __context__, profile)
