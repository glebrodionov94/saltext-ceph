"""Manage Ceph monitor configuration through the Dashboard REST API."""

from saltext.ceph.utils.ceph import cluster_configuration_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_cluster_config"
__func_alias__ = {"list_": "list", "filter_": "filter", "set_": "set"}


def __virtual__():
    return __virtualname__


def list_(profile="default"):
    """Return every configuration option.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster_config.list
    """
    return salt_adapter.invoke(
        cluster_configuration_api.list_, __opts__, __pillar__, __context__, profile
    )


def get(name, profile="default"):
    """Return one configuration option and its section values.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster_config.get mon_allow_pool_delete
    """
    return salt_adapter.invoke(
        cluster_configuration_api.get, __opts__, __pillar__, __context__, name, profile
    )


def filter_(names, profile="default"):
    """Return known options from a list of names.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster_config.filter \\
          '["osd_max_backfills","osd_recovery_sleep"]'
    """
    return salt_adapter.invoke(
        cluster_configuration_api.filter_, __opts__, __pillar__, __context__, names, profile
    )


def set_(name, values, force_update=None, profile="default"):
    """Set or remove explicit section values for one option.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster_config.set debug_ms \\
          '[{"section":"mon","value":"0/3"}]'
    """
    return salt_adapter.invoke(
        cluster_configuration_api.set_,
        __opts__,
        __pillar__,
        __context__,
        name,
        values,
        force_update,
        profile,
    )


def remove(name, section, profile="default"):
    """Remove an option value from one section.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster_config.remove debug_ms mon
    """
    return salt_adapter.invoke(
        cluster_configuration_api.remove,
        __opts__,
        __pillar__,
        __context__,
        name,
        section,
        profile,
    )


def bulk_set(options, profile="default"):
    """Set several option/section pairs in one request.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster_config.bulk_set \\
          '{"osd_max_backfills":{"section":"osd","value":1}}'
    """
    return salt_adapter.invoke(
        cluster_configuration_api.bulk_set,
        __opts__,
        __pillar__,
        __context__,
        options,
        profile,
    )
