"""Salt-facing composition for Dashboard summary inspection."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import summary


def get(opts, pillar, context, profile="default"):
    """Return Dashboard's aggregate summary."""
    client = ceph.get_client(opts, pillar, context, profile)
    return summary.get(client).as_dict()
