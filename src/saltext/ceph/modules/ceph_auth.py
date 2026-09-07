"""Manage the client session with the Ceph Dashboard REST API.

The extension must be installed in the Python environment used by ``salt-call``
or the minion. Connection profiles are read from ``ceph:profiles`` in minion
configuration or pillar. Credentials and JWTs are never included in returns.
"""

from saltext.ceph.utils.ceph import auth
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_auth"


def __virtual__():
    return __virtualname__


def login(profile="default", ttl=None):
    """Authenticate and return public session metadata.

    ``ttl`` is an optional positive number of hours supported by newer Ceph
    versions. Leave it unset for compatibility with Reef.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_auth.login
    """
    return salt_adapter.invoke(auth.login, __opts__, __pillar__, __context__, profile, ttl)


def check(profile="default"):
    """Validate the current JWT and return identity and permission metadata.

    Ceph transmits the token as a query parameter for this endpoint. Disable query
    logging on intermediate proxies before using this operation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_auth.check
    """
    return salt_adapter.invoke(auth.check, __opts__, __pillar__, __context__, profile)


def logout(profile="default"):
    """Revoke the current JWT and discard the local cached session.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_auth.logout
    """
    return salt_adapter.invoke(auth.logout, __opts__, __pillar__, __context__, profile)
