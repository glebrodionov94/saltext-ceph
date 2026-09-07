"""Manage the current Ceph Dashboard message of the day through its REST API."""

from saltext.ceph.utils.ceph import motd_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_motd"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, *args)


def create(severity, expires, message, profile="default"):
    """Set a Dashboard message with a relative expiry.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_motd.create warning 2h 'Maintenance starts soon'
    """
    return _invoke(motd_api.create, severity, expires, message, profile)


def clear(confirm=False, profile="default"):
    """Clear the Dashboard message after explicit confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_motd.clear confirm=true
    """
    return _invoke(motd_api.clear, confirm, profile)
