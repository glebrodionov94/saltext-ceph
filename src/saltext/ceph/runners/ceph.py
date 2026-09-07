"""Inspect a Ceph Dashboard connection from the Salt master.

Configure ``ceph:profiles`` in the master configuration before using this
runner.  Profiles are resolved only from ``__opts__`` because runner modules do
not compile minion pillar.
"""

import re

from salt.exceptions import SaltRunnerError

from saltext.ceph.utils import ceph as ceph_utils
from saltext.ceph.utils.ceph import health
from saltext.ceph.utils.ceph import task
from saltext.ceph.utils.ceph.errors import CephError

__virtualname__ = "ceph"


def __virtual__():
    return __virtualname__


def _profile(value, allow_all=False):
    if value is None and allow_all:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise SaltRunnerError("profile must be a bounded profile name.")
    return value


def _client(profile):
    profile = _profile(profile)
    try:
        return ceph_utils.get_client(__opts__, {}, __context__, profile)
    except CephError as exc:
        raise SaltRunnerError(str(exc)) from None


def _invoke(function, *args):
    try:
        return function(*args)
    except CephError as exc:
        raise SaltRunnerError(str(exc)) from None


def ping(profile="default"):
    """Return the FSID after authenticating to the configured cluster.

    CLI Example:

    .. code-block:: bash

        salt-run ceph.ping profile=default
    """
    return _invoke(health.fsid, _client(profile)).as_dict()


def tasks(name=None, include_secrets=False, profile="default"):
    """Return executing and recently finished Dashboard tasks."""
    return _invoke(task.list_, _client(profile), name, include_secrets).as_dict()


def wait_task(
    name,
    metadata=None,
    timeout=300.0,
    interval=2.0,
    fail_on_error=True,
    include_secrets=False,
    profile="default",
):
    """Wait for the newest Dashboard task matching ``name`` and ``metadata``."""
    return _invoke(
        task.wait,
        _client(profile),
        name,
        metadata,
        timeout,
        interval,
        fail_on_error,
        include_secrets,
    ).as_dict()


def clear_cache(profile="default"):
    """Close one cached master-side API session, or all with ``profile=None``."""
    return ceph_utils.clear_cache(__context__, _profile(profile, allow_all=True))
