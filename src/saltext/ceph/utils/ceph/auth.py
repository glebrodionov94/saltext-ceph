"""Authentication operations shared by Salt execution and SSH wrapper loaders."""

from saltext.ceph.utils import ceph


def login(opts, pillar, context, profile="default", ttl=None):
    """Create a Dashboard session and return public session metadata."""
    client = ceph.get_client(opts, pillar, context, profile)
    return client.login(ttl=ttl).as_dict()


def check(opts, pillar, context, profile="default"):
    """Validate the cached or configured JWT and return identity metadata."""
    client = ceph.get_client(opts, pillar, context, profile)
    return client.check().as_dict()


def logout(opts, pillar, context, profile="default"):
    """Revoke the JWT, return the server response and discard the local client."""
    client = ceph.get_client(opts, pillar, context, profile)
    try:
        return client.logout().as_dict()
    finally:
        ceph.clear_cache(context, profile)
