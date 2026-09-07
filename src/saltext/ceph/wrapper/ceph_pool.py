"""Manage RADOS pools from the salt-ssh controller."""

from saltext.ceph.utils.ceph import pool_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_pool"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(attrs=None, stats=False, profile="default"):
    """List RADOS pools."""
    return _invoke(pool_api.list_, attrs, stats, profile)


def get(pool_name, attrs=None, stats=False, profile="default"):
    """Return one RADOS pool."""
    return _invoke(pool_api.get, pool_name, attrs, stats, profile)


def configuration(pool_name, profile="default"):
    """Return RBD configuration entries stored on a pool."""
    return _invoke(pool_api.configuration, pool_name, profile)


def create(
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
    """Create a RADOS pool."""
    return _invoke(
        pool_api.create,
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
        profile,
    )


def update(
    pool_name,
    new_name=None,
    flags=None,
    application_metadata=None,
    rbd_configuration=None,
    rbd_mirroring=None,
    options=None,
    profile="default",
):
    """Update mutable RADOS pool values."""
    return _invoke(
        pool_api.update,
        pool_name,
        new_name,
        flags,
        application_metadata,
        rbd_configuration,
        rbd_mirroring,
        options,
        profile,
    )


def delete(pool_name, confirm=False, profile="default"):
    """Permanently delete a RADOS pool after explicit confirmation."""
    return _invoke(pool_api.delete, pool_name, confirm, profile)
