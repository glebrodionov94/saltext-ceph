"""Salt-facing composition for cluster configuration operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import cluster_configuration


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, profile="default"):
    """Return all cluster configuration options."""
    return cluster_configuration.list_(_client(opts, pillar, context, profile)).as_dict()


def get(opts, pillar, context, name, profile="default"):
    """Return one cluster configuration option."""
    return cluster_configuration.get(_client(opts, pillar, context, profile), name).as_dict()


def filter_(opts, pillar, context, names, profile="default"):
    """Return known cluster configuration options from a list of names."""
    return cluster_configuration.filter_(_client(opts, pillar, context, profile), names).as_dict()


def set_(opts, pillar, context, name, values, force_update=None, profile="default"):
    """Set or remove section values for one option."""
    return cluster_configuration.set_(
        _client(opts, pillar, context, profile), name, values, force_update
    ).as_dict()


def remove(opts, pillar, context, name, section, profile="default"):
    """Remove one option value from a configuration section."""
    return cluster_configuration.remove(
        _client(opts, pillar, context, profile), name, section
    ).as_dict()


def bulk_set(opts, pillar, context, options, profile="default"):
    """Set several cluster configuration values in one request."""
    return cluster_configuration.bulk_set(
        _client(opts, pillar, context, profile), options
    ).as_dict()
