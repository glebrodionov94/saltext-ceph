"""Inspect Ceph cluster health from salt-ssh."""

from saltext.ceph.utils.ceph import health_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_health"


def __virtual__():
    return __virtualname__


def _invoke(function, profile):
    return salt_adapter.invoke(function, __opts__, {}, __context__, profile)


def full(profile="default"):
    """Return detailed cluster health."""
    return _invoke(health_api.full, profile)


def minimal(profile="default"):
    """Return compact cluster health."""
    return _invoke(health_api.minimal, profile)


def capacity(profile="default"):
    """Return aggregate cluster capacity."""
    return _invoke(health_api.capacity, profile)


def fsid(profile="default"):
    """Return the cluster FSID."""
    return _invoke(health_api.fsid, profile)


def telemetry_enabled(profile="default"):
    """Return whether the telemetry manager module is enabled."""
    return _invoke(health_api.telemetry_enabled, profile)


def snapshot(profile="default"):
    """Return the current-release status-like health snapshot."""
    return _invoke(health_api.snapshot, profile)
