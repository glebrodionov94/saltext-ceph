"""Inspect Ceph Dashboard feature availability from salt-ssh."""

from saltext.ceph.utils.ceph import feature_toggles_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_feature_toggles"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(profile="default"):
    """Return the enabled status of each Dashboard feature."""
    return salt_adapter.invoke(feature_toggles_api.list_, __opts__, {}, __context__, profile)
