"""Manage CRUSH rules from the salt-ssh controller."""

from saltext.ceph.utils.ceph import crush_rule_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_crush_rule"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(profile="default"):
    """Return all CRUSH rules."""
    return _invoke(crush_rule_api.list_, profile)


def get(name, profile="default"):
    """Return one CRUSH rule by name."""
    return _invoke(crush_rule_api.get, name, profile)


def create(
    name,
    failure_domain,
    device_class=None,
    root=None,
    erasure_profile=None,
    pool_type="replication",
    profile="default",
):
    """Create a replicated or erasure CRUSH rule."""
    return _invoke(
        crush_rule_api.create,
        name,
        failure_domain,
        device_class,
        root,
        erasure_profile,
        pool_type,
        profile,
    )


def delete(name, confirm=False, profile="default"):
    """Delete one CRUSH rule after explicit confirmation."""
    return _invoke(crush_rule_api.delete, name, confirm, profile)
