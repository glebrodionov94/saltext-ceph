"""Salt-facing composition for cluster status and cephadm upgrades."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import cluster


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def status(opts, pillar, context, profile="default"):
    """Return the Dashboard cluster status marker."""
    return cluster.status(_client(opts, pillar, context, profile)).as_dict()


def set_status(opts, pillar, context, cluster_status, profile="default"):
    """Set the Dashboard cluster status marker."""
    return cluster.set_status(_client(opts, pillar, context, profile), cluster_status).as_dict()


def upgrade_list(
    opts, pillar, context, tags=False, image=None, show_all_versions=False, profile="default"
):
    """List available upgrade targets."""
    return cluster.upgrade_list(
        _client(opts, pillar, context, profile), tags, image, show_all_versions
    ).as_dict()


def upgrade_status(opts, pillar, context, profile="default"):
    """Return cephadm upgrade progress."""
    return cluster.upgrade_status(_client(opts, pillar, context, profile)).as_dict()


def upgrade_start(
    opts,
    pillar,
    context,
    image=None,
    version=None,
    daemon_types=None,
    host_placement=None,
    services=None,
    limit=None,
    profile="default",
):
    """Start a cephadm upgrade."""
    return cluster.upgrade_start(
        _client(opts, pillar, context, profile),
        image,
        version,
        daemon_types,
        host_placement,
        services,
        limit,
    ).as_dict()


def upgrade_pause(opts, pillar, context, profile="default"):
    """Pause an active cephadm upgrade."""
    return cluster.upgrade_pause(_client(opts, pillar, context, profile)).as_dict()


def upgrade_resume(opts, pillar, context, profile="default"):
    """Resume a paused cephadm upgrade."""
    return cluster.upgrade_resume(_client(opts, pillar, context, profile)).as_dict()


def upgrade_stop(opts, pillar, context, profile="default"):
    """Stop an active cephadm upgrade."""
    return cluster.upgrade_stop(_client(opts, pillar, context, profile)).as_dict()
