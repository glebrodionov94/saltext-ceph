"""Salt-facing composition for cephadm daemon operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import daemon


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, daemon_types=None, profile="default"):
    """List cephadm daemons."""
    return daemon.list_(_client(opts, pillar, context, profile), daemon_types).as_dict()


def action(
    opts,
    pillar,
    context,
    daemon_name,
    action_name,
    container_image=None,
    force=False,
    profile="default",
):
    """Schedule an action for one cephadm daemon."""
    return daemon.action(
        _client(opts, pillar, context, profile),
        daemon_name,
        action_name,
        container_image,
        force,
    ).as_dict()
