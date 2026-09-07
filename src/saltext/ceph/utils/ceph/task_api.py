"""Salt-facing composition for Dashboard task operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import task


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, name=None, include_secrets=False, profile="default"):
    """Return Dashboard tasks."""
    return task.list_(_client(opts, pillar, context, profile), name, include_secrets).as_dict()


def wait(
    opts,
    pillar,
    context,
    name,
    metadata=None,
    timeout=300.0,
    interval=2.0,
    fail_on_error=True,
    include_secrets=False,
    profile="default",
):
    """Wait for one Dashboard task to finish."""
    return task.wait(
        _client(opts, pillar, context, profile),
        name,
        metadata,
        timeout,
        interval,
        fail_on_error,
        include_secrets,
    ).as_dict()
