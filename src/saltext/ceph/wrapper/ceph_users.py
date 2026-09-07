"""Manage CephX users from the salt-ssh controller."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import user_api

__virtualname__ = "ceph_users"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(profile="default"):
    """List CephX users through the controller profile."""
    return _invoke(user_api.list_, profile)


def get(user_entity, profile="default"):
    """Return one CephX user, or ``None`` when absent."""
    return _invoke(user_api.get, user_entity, profile)


def create(user_entity, capabilities, profile="default"):
    """Create a CephX user."""
    return _invoke(user_api.create, user_entity, capabilities, profile)


def update(user_entity, capabilities, profile="default"):
    """Replace all capabilities of a CephX user."""
    return _invoke(user_api.update, user_entity, capabilities, profile)


def delete(user_entity, confirm=False, profile="default"):
    """Delete one CephX user after explicit confirmation."""
    return _invoke(user_api.delete, user_entity, confirm, profile)


def import_keyring(source, profile="default"):
    """Import a controller-local keyring without returning its contents."""
    return _invoke(user_api.import_keyring, source, profile)


def export_keyring(entities, destination, overwrite=False, profile="default"):
    """Export keyrings into a controller-local file."""
    return _invoke(user_api.export_keyring, entities, destination, overwrite, profile)
