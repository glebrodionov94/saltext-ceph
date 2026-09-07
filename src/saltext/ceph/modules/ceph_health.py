"""Inspect Ceph cluster health through the Dashboard REST API."""

from saltext.ceph.utils.ceph import health_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_health"


def __virtual__():
    return __virtualname__


def _invoke(function, profile):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, profile)


def full(profile="default"):
    """Return detailed cluster health.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_health.full
    """
    return _invoke(health_api.full, profile)


def minimal(profile="default"):
    """Return compact cluster health.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_health.minimal
    """
    return _invoke(health_api.minimal, profile)


def capacity(profile="default"):
    """Return aggregate cluster capacity.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_health.capacity
    """
    return _invoke(health_api.capacity, profile)


def fsid(profile="default"):
    """Return the cluster FSID.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_health.fsid
    """
    return _invoke(health_api.fsid, profile)


def telemetry_enabled(profile="default"):
    """Return whether the telemetry manager module is enabled.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_health.telemetry_enabled
    """
    return _invoke(health_api.telemetry_enabled, profile)


def snapshot(profile="default"):
    """Return the current-release status-like health snapshot.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_health.snapshot
    """
    return _invoke(health_api.snapshot, profile)
