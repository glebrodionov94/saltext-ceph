"""Manage public Ceph Dashboard RGW daemon operations."""

from saltext.ceph.utils.ceph import rgw_daemon_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rgw_daemon"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, *args)


def list_daemons(profile="default"):
    """List RGW daemons.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_daemon.list_daemons
    """
    return _invoke(rgw_daemon_api.list_daemons, profile)


def get_daemon(service_id, profile="default"):
    """Return one RGW daemon.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_daemon.get_daemon service_id
    """
    return _invoke(rgw_daemon_api.get_daemon, service_id, profile)


def set_multisite_config(
    realm_name=None, zonegroup_name=None, zone_name=None, daemon_name=None, profile="default"
):
    """Set Dashboard's selected multisite configuration.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_daemon.set_multisite_config
    """
    return _invoke(
        rgw_daemon_api.set_multisite_config,
        realm_name,
        zonegroup_name,
        zone_name,
        daemon_name,
        profile,
    )


def get_site(query, daemon_name=None, profile="default"):
    """Run a supported RGW site query.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_daemon.get_site query
    """
    return _invoke(rgw_daemon_api.get_site, query, daemon_name, profile)
