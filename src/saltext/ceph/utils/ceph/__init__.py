"""Salt utilities shared by execution, state, runner, beacon and SSH loaders.

Caller context is explicit: these helpers do not read implicit Salt globals.
"""

from saltext.ceph.utils.ceph import session

__virtualname__ = "ceph"


def __virtual__():
    return __virtualname__


def get_client(opts, pillar, context, profile="default"):
    """Resolve a profile and return its cached HTTP client."""
    return session.get_client(opts, pillar, context, profile)


def clear_cache(context, profile="default"):
    """Discard a cached session, or all sessions when ``profile=None``."""
    return session.clear_cache(context, profile)
