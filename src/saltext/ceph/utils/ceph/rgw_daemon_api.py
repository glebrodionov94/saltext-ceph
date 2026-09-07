"""Salt-facing composition for public RGW daemon and site operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rgw_daemon


def _call(operation, opts, pillar, context, profile, *args, **kwargs):
    client = ceph.get_client(opts, pillar, context, profile)
    return operation(client, *args, **kwargs).as_dict()


def list_daemons(opts, pillar, context, profile="default"):
    """List RGW daemons."""
    return _call(rgw_daemon.list_daemons, opts, pillar, context, profile)


def get_daemon(opts, pillar, context, service_id, profile="default"):
    """Return one RGW daemon."""
    return _call(rgw_daemon.get_daemon, opts, pillar, context, profile, service_id)


def set_multisite_config(
    opts,
    pillar,
    context,
    realm_name=None,
    zonegroup_name=None,
    zone_name=None,
    daemon_name=None,
    profile="default",
):
    """Set Dashboard's selected multisite configuration."""
    return _call(
        rgw_daemon.set_multisite_config,
        opts,
        pillar,
        context,
        profile,
        realm_name,
        zonegroup_name,
        zone_name,
        daemon_name,
    )


def get_site(opts, pillar, context, query, daemon_name=None, profile="default"):
    """Run a supported RGW site query."""
    return _call(rgw_daemon.get_site, opts, pillar, context, profile, query, daemon_name)
