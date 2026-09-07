"""Inspect and operate cephadm daemons through the Dashboard REST API."""

from saltext.ceph.utils.ceph import daemon_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_daemon"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(daemon_types=None, profile="default"):
    """List all daemons or filter by daemon types.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_daemon.list daemon_types='["mon","mgr"]'
    """
    return salt_adapter.invoke(
        daemon_api.list_, __opts__, __pillar__, __context__, daemon_types, profile
    )


def action(
    daemon_name,
    action_name,
    container_image=None,
    force=False,
    profile="default",
):
    """Schedule ``start``, ``stop``, ``restart``, or ``redeploy``.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_daemon.action osd.1 restart
    """
    return salt_adapter.invoke(
        daemon_api.action,
        __opts__,
        __pillar__,
        __context__,
        daemon_name,
        action_name,
        container_image,
        force,
        profile,
    )
