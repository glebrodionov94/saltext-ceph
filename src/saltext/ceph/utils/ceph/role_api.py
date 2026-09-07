"""Salt-facing composition for Dashboard role operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import role


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, profile="default"):
    """List Dashboard roles."""
    return role.list_(_client(opts, pillar, context, profile)).as_dict()


def get(opts, pillar, context, name, profile="default"):
    """Return one Dashboard role."""
    return role.get(_client(opts, pillar, context, profile), name).as_dict()


def create(
    opts,
    pillar,
    context,
    name,
    description=None,
    scopes_permissions=None,
    profile="default",
):
    """Create a Dashboard role."""
    return role.create(
        _client(opts, pillar, context, profile), name, description, scopes_permissions
    ).as_dict()


def update(
    opts,
    pillar,
    context,
    name,
    description=None,
    scopes_permissions=None,
    profile="default",
):
    """Replace a Dashboard role's mutable fields."""
    return role.update(
        _client(opts, pillar, context, profile), name, description, scopes_permissions
    ).as_dict()


def delete(opts, pillar, context, name, confirm=False, profile="default"):
    """Delete a custom Dashboard role after explicit confirmation."""
    return role.delete(_client(opts, pillar, context, profile), name, confirm).as_dict()


def clone(opts, pillar, context, name, new_name, profile="default"):
    """Clone a Dashboard role."""
    return role.clone(_client(opts, pillar, context, profile), name, new_name).as_dict()
