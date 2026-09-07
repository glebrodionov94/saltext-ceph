"""Manage Ceph Dashboard roles from the salt-ssh controller."""

from saltext.ceph.utils.ceph import role_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_role"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(profile="default"):
    """List custom and built-in Dashboard roles."""
    return _invoke(role_api.list_, profile)


def get(name, profile="default"):
    """Return one Dashboard role."""
    return _invoke(role_api.get, name, profile)


def create(name, description=None, scopes_permissions=None, profile="default"):
    """Create a Dashboard role."""
    return _invoke(role_api.create, name, description, scopes_permissions, profile)


def update(name, description=None, scopes_permissions=None, profile="default"):
    """Replace a custom role's mutable fields."""
    return _invoke(role_api.update, name, description, scopes_permissions, profile)


def delete(name, confirm=False, profile="default"):
    """Delete a custom Dashboard role after explicit confirmation."""
    return _invoke(role_api.delete, name, confirm, profile)


def clone(name, new_name, profile="default"):
    """Clone a Dashboard role."""
    return _invoke(role_api.clone, name, new_name, profile)
