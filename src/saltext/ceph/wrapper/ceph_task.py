"""Inspect and wait for Ceph Dashboard tasks from salt-ssh."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import task_api

__virtualname__ = "ceph_task"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(name=None, include_secrets=False, profile="default"):
    """Return executing and finished tasks."""
    return _invoke(task_api.list_, name, include_secrets, profile)


def wait(
    name,
    metadata=None,
    timeout=300.0,
    interval=2.0,
    fail_on_error=True,
    include_secrets=False,
    profile="default",
):
    """Wait for the newest matching task to finish."""
    return _invoke(
        task_api.wait,
        name,
        metadata,
        timeout,
        interval,
        fail_on_error,
        include_secrets,
        profile,
    )
