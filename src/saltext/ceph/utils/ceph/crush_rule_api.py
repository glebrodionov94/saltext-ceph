"""Salt-facing composition for CRUSH rule operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import crush_rule


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, profile="default"):
    """Return all CRUSH rules."""
    return crush_rule.list_(_client(opts, pillar, context, profile)).as_dict()


def get(opts, pillar, context, name, profile="default"):
    """Return one CRUSH rule."""
    return crush_rule.get(_client(opts, pillar, context, profile), name).as_dict()


def create(
    opts,
    pillar,
    context,
    name,
    failure_domain,
    device_class=None,
    root=None,
    erasure_profile=None,
    pool_type="replication",
    profile="default",
):
    """Create a replicated or erasure CRUSH rule."""
    return crush_rule.create(
        _client(opts, pillar, context, profile),
        name,
        failure_domain,
        device_class,
        root,
        erasure_profile,
        pool_type,
    ).as_dict()


def delete(opts, pillar, context, name, confirm=False, profile="default"):
    """Delete one CRUSH rule after explicit confirmation."""
    return crush_rule.delete(_client(opts, pillar, context, profile), name, confirm).as_dict()
