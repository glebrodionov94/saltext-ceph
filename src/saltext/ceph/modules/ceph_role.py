"""Manage Ceph Dashboard roles through the Dashboard REST API."""

from saltext.ceph.utils.ceph import role_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_role"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(profile="default"):
    """List custom and built-in Dashboard roles.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_role.list
    """
    return salt_adapter.invoke(role_api.list_, __opts__, __pillar__, __context__, profile)


def get(name, profile="default"):
    """Return one Dashboard role.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_role.get backup-manager
    """
    return salt_adapter.invoke(role_api.get, __opts__, __pillar__, __context__, name, profile)


def create(name, description=None, scopes_permissions=None, profile="default"):
    """Create a Dashboard role.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_role.create backup-manager \\
          scopes_permissions='{"pool":["read"],"rbd-image":["read","create"]}'
    """
    return salt_adapter.invoke(
        role_api.create,
        __opts__,
        __pillar__,
        __context__,
        name,
        description,
        scopes_permissions,
        profile,
    )


def update(name, description=None, scopes_permissions=None, profile="default"):
    """Replace a custom role's description and complete permissions mapping.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_role.update backup-manager \\
          description='Backup operators' scopes_permissions='{"pool":["read"]}'
    """
    return salt_adapter.invoke(
        role_api.update,
        __opts__,
        __pillar__,
        __context__,
        name,
        description,
        scopes_permissions,
        profile,
    )


def delete(name, confirm=False, profile="default"):
    """Delete a custom Dashboard role after explicit confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_role.delete backup-manager confirm=true
    """
    return salt_adapter.invoke(
        role_api.delete, __opts__, __pillar__, __context__, name, confirm, profile
    )


def clone(name, new_name, profile="default"):
    """Clone a Dashboard role under a new name.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_role.clone backup-manager backup-manager-copy
    """
    return salt_adapter.invoke(
        role_api.clone, __opts__, __pillar__, __context__, name, new_name, profile
    )
