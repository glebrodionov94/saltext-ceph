"""Access the Ceph Dashboard API from the salt-ssh controller.

Install this extension on the controller. Connection profiles are read from its
``__opts__`` only, so selecting a roster target cannot change the HTTP destination
or supply credentials. Configure ``ceph:profiles`` in the salt-ssh configuration.
"""

from salt.exceptions import SaltInvocationError

from saltext.ceph.utils import ceph as ceph_utils
from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import validation

__virtualname__ = "ceph"


def __virtual__():
    return __virtualname__


def query(
    path,
    api_version,
    method="GET",
    params=None,
    data=None,
    profile="default",
    confirm=False,
):
    """Return ``status``, ``data`` and selected ``headers`` from a Ceph request.

    This is a low-level API call, not an idempotent state. Mutations require the
    real boolean ``confirm=True`` and are refused when Salt's test option is set.
    Never pass secrets on the command line.

    CLI Example:

    .. code-block:: bash

        salt-ssh ceph-admin ceph.query /api/health/minimal api_version='"1.0"'
    """
    if not isinstance(method, str) or method.upper() not in (
        "GET",
        "HEAD",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    ):
        raise SaltInvocationError("Unsupported HTTP method.")
    normalized_method = method.upper()
    if __opts__.get("test") and normalized_method not in ("GET", "HEAD"):
        raise SaltInvocationError("Ceph API mutations cannot run with test=True.")
    if normalized_method not in ("GET", "HEAD"):
        salt_adapter.invoke(
            validation.confirmation,
            confirm,
            f"Low-level {normalized_method} request",
        )
    # Salt CLI YAML parsing converts an unquoted 1.0 into a float.
    if isinstance(api_version, (int, float)) and not isinstance(api_version, bool):
        raise SaltInvocationError("Quote api_version as a string, for example '\"1.0\"'.")
    client = salt_adapter.invoke(ceph_utils.get_client, __opts__, {}, __context__, profile)
    return salt_adapter.invoke(
        client.request,
        normalized_method,
        path,
        api_version=api_version,
        params=params,
        data=data,
    ).as_dict()


def clear_cache(profile="default"):
    """Discard a local session. ``profile=None`` clears all cached sessions.

    This neither logs out nor revokes the token on the Ceph server.
    """
    return ceph_utils.clear_cache(__context__, profile)
