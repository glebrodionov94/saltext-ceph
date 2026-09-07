"""Salt-facing composition for hardware controller operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import hardware


def summary(opts, pillar, context, categories=None, hostnames=None, profile="default"):
    """Return orchestrator hardware health totals."""
    client = ceph.get_client(opts, pillar, context, profile)
    return hardware.summary(client, categories, hostnames).as_dict()
