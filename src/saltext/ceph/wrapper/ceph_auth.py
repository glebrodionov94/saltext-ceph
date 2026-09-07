"""Manage Ceph Dashboard authentication from the salt-ssh controller."""

from saltext.ceph.utils.ceph import auth
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_auth"


def __virtual__():
    return __virtualname__


def login(profile="default", ttl=None):
    """Authenticate using a controller profile without returning its JWT."""
    return salt_adapter.invoke(auth.login, __opts__, {}, __context__, profile, ttl)


def check(profile="default"):
    """Validate the controller's current JWT and return public identity data."""
    return salt_adapter.invoke(auth.check, __opts__, {}, __context__, profile)


def logout(profile="default"):
    """Revoke the controller's JWT and discard its local session."""
    return salt_adapter.invoke(auth.logout, __opts__, {}, __context__, profile)
