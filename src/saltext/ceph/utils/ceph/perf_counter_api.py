"""Salt-facing composition for performance-counter inspection."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import perf_counter


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, profile="default"):
    """Return all unlabeled performance counters."""
    return perf_counter.list_(_client(opts, pillar, context, profile)).as_dict()


def get(opts, pillar, context, service_type, service_id, profile="default"):
    """Return counters for one daemon service."""
    return perf_counter.get(
        _client(opts, pillar, context, profile), service_type, service_id
    ).as_dict()
