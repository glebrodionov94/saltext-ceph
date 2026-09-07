"""Salt-facing composition for Dashboard feature-toggle inspection."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import feature_toggles


def list_(opts, pillar, context, profile="default"):
    """Return the Dashboard feature names and their enabled status."""
    client = ceph.get_client(opts, pillar, context, profile)
    return feature_toggles.list_(client).as_dict()
