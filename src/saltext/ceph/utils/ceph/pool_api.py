"""Salt-facing composition for pool operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import pool


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, attrs=None, stats=False, profile="default"):
    """Return pools."""
    return pool.list_(_client(opts, pillar, context, profile), attrs, stats).as_dict()


def get(opts, pillar, context, pool_name, attrs=None, stats=False, profile="default"):
    """Return one pool."""
    return pool.get(_client(opts, pillar, context, profile), pool_name, attrs, stats).as_dict()


def configuration(opts, pillar, context, pool_name, profile="default"):
    """Return one pool's RBD configuration."""
    return pool.configuration(_client(opts, pillar, context, profile), pool_name).as_dict()


def create(
    opts,
    pillar,
    context,
    pool_name,
    pg_num,
    pool_type,
    erasure_code_profile=None,
    flags=None,
    application_metadata=None,
    rule_name=None,
    rbd_configuration=None,
    rbd_mirroring=None,
    options=None,
    profile="default",
):
    """Create a pool."""
    return pool.create(
        _client(opts, pillar, context, profile),
        pool_name,
        pg_num,
        pool_type,
        erasure_code_profile,
        flags,
        application_metadata,
        rule_name,
        rbd_configuration,
        rbd_mirroring,
        options,
    ).as_dict()


def update(
    opts,
    pillar,
    context,
    pool_name,
    new_name=None,
    flags=None,
    application_metadata=None,
    rbd_configuration=None,
    rbd_mirroring=None,
    options=None,
    profile="default",
):
    """Update a pool."""
    return pool.update(
        _client(opts, pillar, context, profile),
        pool_name,
        new_name,
        flags,
        application_metadata,
        rbd_configuration,
        rbd_mirroring,
        options,
    ).as_dict()


def delete(opts, pillar, context, pool_name, confirm=False, profile="default"):
    """Delete a pool after explicit confirmation."""
    return pool.delete(_client(opts, pillar, context, profile), pool_name, confirm).as_dict()
