"""Salt-facing composition for erasure-code profile operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import erasure_code_profile


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, profile="default"):
    """Return all erasure-code profiles."""
    return erasure_code_profile.list_(_client(opts, pillar, context, profile)).as_dict()


def get(opts, pillar, context, name, profile="default"):
    """Return one erasure-code profile."""
    return erasure_code_profile.get(_client(opts, pillar, context, profile), name).as_dict()


def create(opts, pillar, context, name, settings=None, profile="default"):
    """Create an erasure-code profile."""
    return erasure_code_profile.create(
        _client(opts, pillar, context, profile), name, settings
    ).as_dict()


def delete(opts, pillar, context, name, confirm=False, profile="default"):
    """Delete one erasure-code profile after explicit confirmation."""
    return erasure_code_profile.delete(
        _client(opts, pillar, context, profile), name, confirm
    ).as_dict()
