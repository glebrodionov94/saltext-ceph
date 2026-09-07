"""Manage Ceph Dashboard settings from the salt-ssh controller."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import settings_api

__virtualname__ = "ceph_settings"
__func_alias__ = {"list_": "list", "set_": "set"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(names=None, profile="default"):
    """List Dashboard settings with secret values redacted."""
    return _invoke(settings_api.list_, names, profile)


def get(name, profile="default"):
    """Return one Dashboard setting with secret values redacted."""
    return _invoke(settings_api.get, name, profile)


def set_(name, value=None, source=None, profile="default"):
    """Set one Dashboard setting."""
    return _invoke(settings_api.set_, name, value, source, profile)


def delete(name, profile="default"):
    """Reset one Dashboard setting to its default."""
    return _invoke(settings_api.delete, name, profile)


def bulk_set(values=None, secret_sources=None, profile="default"):
    """Set several Dashboard settings."""
    return _invoke(settings_api.bulk_set, values, secret_sources, profile)
