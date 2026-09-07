"""Salt-facing composition for monitor status inspection."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import monitor


def status(opts, pillar, context, profile="default"):
    """Return monitor status and quorum membership."""
    client = ceph.get_client(opts, pillar, context, profile)
    return monitor.status(client).as_dict()
