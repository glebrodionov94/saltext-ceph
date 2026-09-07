"""Inspect and control Ceph telemetry from the salt-ssh controller."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import telemetry_api

__virtualname__ = "ceph_telemetry"
__func_alias__ = {"set_": "set"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def report(profile="default"):
    """Return the cluster and device telemetry preview."""
    return _invoke(telemetry_api.report, profile)


def set_(enable=True, license_name=None, profile="default"):
    """Enable or disable periodic telemetry submission."""
    return _invoke(telemetry_api.set_, enable, license_name, profile)
