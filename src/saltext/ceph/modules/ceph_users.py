"""Manage CephX users through the Ceph Dashboard REST API.

These are Ceph authentication entities such as ``client.backup``, not Dashboard
login users. Mutating functions are execution operations; use the matching state
module when idempotent reconciliation is required.
"""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import user_api

__virtualname__ = "ceph_users"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(profile="default"):
    """List CephX users; key values are masked by Dashboard.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_users.list
    """
    return salt_adapter.invoke(user_api.list_, __opts__, __pillar__, __context__, profile)


def get(user_entity, profile="default"):
    """Return one CephX user, or ``None`` when absent.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_users.get client.backup
    """
    return salt_adapter.invoke(
        user_api.get, __opts__, __pillar__, __context__, user_entity, profile
    )


def create(user_entity, capabilities, profile="default"):
    """Create a CephX user with a complete list of capabilities.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_users.create client.backup \\
          '[{"entity":"mon","cap":"allow r"}]'
    """
    return salt_adapter.invoke(
        user_api.create,
        __opts__,
        __pillar__,
        __context__,
        user_entity,
        capabilities,
        profile,
    )


def update(user_entity, capabilities, profile="default"):
    """Replace all capabilities of an existing CephX user.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_users.update client.backup \\
          '[{"entity":"mon","cap":"allow r"},{"entity":"osd","cap":"allow rw pool=backups"}]'
    """
    return salt_adapter.invoke(
        user_api.update,
        __opts__,
        __pillar__,
        __context__,
        user_entity,
        capabilities,
        profile,
    )


def delete(user_entity, confirm=False, profile="default"):
    """Delete one CephX user after explicit confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_users.delete client.backup confirm=true
    """
    return salt_adapter.invoke(
        user_api.delete, __opts__, __pillar__, __context__, user_entity, confirm, profile
    )


def import_keyring(source, profile="default"):
    """Import an absolute local keyring file without returning its contents.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_users.import_keyring /run/secrets/ceph.keyring
    """
    return salt_adapter.invoke(
        user_api.import_keyring, __opts__, __pillar__, __context__, source, profile
    )


def export_keyring(entities, destination, overwrite=False, profile="default"):
    """Export keyrings into a local file without placing them in Salt returns.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_users.export_keyring \\
          '["client.backup"]' /run/secrets/client.backup.keyring
    """
    return salt_adapter.invoke(
        user_api.export_keyring,
        __opts__,
        __pillar__,
        __context__,
        entities,
        destination,
        overwrite,
        profile,
    )
