"""Inspect and operate cephadm daemons from the salt-ssh controller."""

from saltext.ceph.utils.ceph import daemon_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_daemon"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(daemon_types=None, profile="default"):
    """List all daemons or filter by daemon types."""
    return _invoke(daemon_api.list_, daemon_types, profile)


def action(
    daemon_name,
    action_name,
    container_image=None,
    force=False,
    profile="default",
):
    """Schedule an action for one cephadm daemon."""
    return _invoke(
        daemon_api.action,
        daemon_name,
        action_name,
        container_image,
        force,
        profile,
    )
