"""Control cluster status and cephadm upgrades from the salt-ssh controller."""

from saltext.ceph.utils.ceph import cluster_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_cluster"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def status(profile="default"):
    """Return the cluster installation status marker."""
    return _invoke(cluster_api.status, profile)


def set_status(cluster_status, profile="default"):
    """Set the cluster installation status marker."""
    return _invoke(cluster_api.set_status, cluster_status, profile)


def upgrade_list(tags=False, image=None, show_all_versions=False, profile="default"):
    """List available cephadm upgrade targets."""
    return _invoke(cluster_api.upgrade_list, tags, image, show_all_versions, profile)


def upgrade_status(profile="default"):
    """Return current cephadm upgrade progress."""
    return _invoke(cluster_api.upgrade_status, profile)


def upgrade_start(
    image=None,
    version=None,
    daemon_types=None,
    host_placement=None,
    services=None,
    limit=None,
    profile="default",
):
    """Start a cephadm upgrade."""
    return _invoke(
        cluster_api.upgrade_start,
        image,
        version,
        daemon_types,
        host_placement,
        services,
        limit,
        profile,
    )


def upgrade_pause(profile="default"):
    """Pause an active cephadm upgrade."""
    return _invoke(cluster_api.upgrade_pause, profile)


def upgrade_resume(profile="default"):
    """Resume a paused cephadm upgrade."""
    return _invoke(cluster_api.upgrade_resume, profile)


def upgrade_stop(profile="default"):
    """Stop an active cephadm upgrade."""
    return _invoke(cluster_api.upgrade_stop, profile)
