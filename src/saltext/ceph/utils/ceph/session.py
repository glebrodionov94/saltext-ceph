"""Profile-scoped clients cached in the caller's Salt ``__context__``."""

from saltext.ceph.utils.ceph.client import CephClient
from saltext.ceph.utils.ceph.config import load_profile
from saltext.ceph.utils.ceph.errors import ConfigurationError

_CACHE_KEY = "saltext.ceph.clients"


def get_client(opts, pillar, context, profile="default"):
    """Reuse a client only while the resolved profile remains unchanged.

    This is an in-memory cache, never a Salt disk cache. Pass the calling loader's
    opts, pillar and context explicitly, including from runners and beacons.
    """
    cache = context.setdefault(_CACHE_KEY, {})
    try:
        config = load_profile(opts, pillar, profile)
    except ConfigurationError:
        if isinstance(profile, str):
            clear_cache(context, profile)
        raise
    client = cache.get(profile)
    if client is not None and (client.closed or client.config != config):
        client.close()
        client = None
    if client is None:
        client = CephClient(config)
        cache[profile] = client
    return client


def clear_cache(context, profile="default"):
    """Close and remove one local session, or all sessions with ``profile=None``."""
    cache = context.get(_CACHE_KEY, {})
    names = list(cache) if profile is None else [profile]
    removed = False
    for name in names:
        client = cache.pop(name, None)
        if client is not None:
            client.close()
            removed = True
    return removed
