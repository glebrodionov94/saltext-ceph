"""Manage cluster configuration from the salt-ssh controller."""

from saltext.ceph.utils.ceph import cluster_configuration_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_cluster_config"
__func_alias__ = {"list_": "list", "filter_": "filter", "set_": "set"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(profile="default"):
    """Return every configuration option."""
    return _invoke(cluster_configuration_api.list_, profile)


def get(name, profile="default"):
    """Return one configuration option and its section values."""
    return _invoke(cluster_configuration_api.get, name, profile)


def filter_(names, profile="default"):
    """Return known options from a list of names."""
    return _invoke(cluster_configuration_api.filter_, names, profile)


def set_(name, values, force_update=None, profile="default"):
    """Set or remove section values for one option."""
    return _invoke(cluster_configuration_api.set_, name, values, force_update, profile)


def remove(name, section, profile="default"):
    """Remove an option value from one section."""
    return _invoke(cluster_configuration_api.remove, name, section, profile)


def bulk_set(options, profile="default"):
    """Set several option/section pairs in one request."""
    return _invoke(cluster_configuration_api.bulk_set, options, profile)
