"""Salt-facing composition for health controller operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import health


def _call(function, opts, pillar, context, profile):
    return function(ceph.get_client(opts, pillar, context, profile)).as_dict()


def full(opts, pillar, context, profile="default"):
    """Return detailed cluster health."""
    return _call(health.full, opts, pillar, context, profile)


def minimal(opts, pillar, context, profile="default"):
    """Return compact cluster health."""
    return _call(health.minimal, opts, pillar, context, profile)


def capacity(opts, pillar, context, profile="default"):
    """Return aggregate cluster capacity."""
    return _call(health.capacity, opts, pillar, context, profile)


def fsid(opts, pillar, context, profile="default"):
    """Return the cluster FSID."""
    return _call(health.fsid, opts, pillar, context, profile)


def telemetry_enabled(opts, pillar, context, profile="default"):
    """Return whether telemetry is enabled."""
    return _call(health.telemetry_enabled, opts, pillar, context, profile)


def snapshot(opts, pillar, context, profile="default"):
    """Return the current-release health snapshot."""
    return _call(health.snapshot, opts, pillar, context, profile)
