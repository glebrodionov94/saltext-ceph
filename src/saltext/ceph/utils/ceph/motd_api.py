"""Salt-facing composition for Dashboard MOTD operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import motd


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def create(opts, pillar, context, severity, expires, message, profile="default"):
    """Set the Dashboard message of the day."""
    return motd.create(
        _client(opts, pillar, context, profile), severity, expires, message
    ).as_dict()


def clear(opts, pillar, context, confirm=False, profile="default"):
    """Clear the Dashboard message of the day."""
    return motd.clear(_client(opts, pillar, context, profile), confirm).as_dict()
