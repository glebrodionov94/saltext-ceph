"""Inspect and control Ceph telemetry through the Dashboard REST API."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import telemetry_api

__virtualname__ = "ceph_telemetry"
__func_alias__ = {"set_": "set"}


def __virtual__():
    return __virtualname__


def report(profile="default"):
    """Return the cluster and device telemetry preview.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_telemetry.report
    """
    return salt_adapter.invoke(telemetry_api.report, __opts__, __pillar__, __context__, profile)


def set_(enable=True, license_name=None, profile="default"):
    """Enable or disable periodic telemetry submission.

    CLI Examples:

    .. code-block:: bash

        salt-call --local ceph_telemetry.set true license_name=sharing-1-0
        salt-call --local ceph_telemetry.set false
    """
    return salt_adapter.invoke(
        telemetry_api.set_,
        __opts__,
        __pillar__,
        __context__,
        enable,
        license_name,
        profile,
    )
