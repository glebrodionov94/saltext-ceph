"""Manage erasure-code profiles from the salt-ssh controller."""

from saltext.ceph.utils.ceph import erasure_code_profile_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_erasure_code_profile"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(profile="default"):
    """Return all erasure-code profiles."""
    return _invoke(erasure_code_profile_api.list_, profile)


def get(name, profile="default"):
    """Return one erasure-code profile by name."""
    return _invoke(erasure_code_profile_api.get, name, profile)


def create(name, settings=None, profile="default"):
    """Create a profile from a mapping of plugin-specific settings."""
    return _invoke(erasure_code_profile_api.create, name, settings, profile)


def delete(name, confirm=False, profile="default"):
    """Delete one erasure-code profile after explicit confirmation."""
    return _invoke(erasure_code_profile_api.delete, name, confirm, profile)
