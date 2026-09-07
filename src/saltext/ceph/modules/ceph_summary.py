"""Read the Ceph Dashboard aggregate summary."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import summary_api

__virtualname__ = "ceph_summary"


def __virtual__():
    return __virtualname__


def get(profile="default"):
    """Return cluster health, manager identity, tasks and mirroring counts.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_summary.get
    """
    return salt_adapter.invoke(summary_api.get, __opts__, __pillar__, __context__, profile)
