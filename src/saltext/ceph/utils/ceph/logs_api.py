"""Salt-facing composition for Dashboard log inspection."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import logs


def all_(opts, pillar, context, profile="default"):
    """Return recent cluster and audit log entries."""
    client = ceph.get_client(opts, pillar, context, profile)
    return logs.all_(client).as_dict()
