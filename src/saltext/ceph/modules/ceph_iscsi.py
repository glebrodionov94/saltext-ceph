"""Manage iSCSI targets through the Ceph Dashboard REST API."""

from saltext.ceph.utils.ceph import iscsi_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_iscsi"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, *args)


def get_discovery_auth(include_secrets=False, profile="default"):
    """Return discovery CHAP configuration, redacting passwords by default.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_iscsi.get_discovery_auth

    ``include_secrets=true`` explicitly exposes CHAP passwords in Salt output.
    """
    return _invoke(iscsi_api.get_discovery_auth, include_secrets, profile)


def set_discovery_auth(
    user="",
    password_source=None,
    mutual_user="",
    mutual_password_source=None,
    profile="default",
):
    """Set discovery CHAP credentials from files; omitted values disable authentication.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_iscsi.set_discovery_auth \\
          user=discovery01 password_source=/run/secrets/iscsi-discovery-password
    """
    return _invoke(
        iscsi_api.set_discovery_auth,
        user,
        password_source,
        mutual_user,
        mutual_password_source,
        profile,
    )


def list_targets(include_secrets=False, profile="default"):
    """List all iSCSI targets, redacting CHAP passwords by default.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_iscsi.list_targets
    """
    return _invoke(iscsi_api.list_targets, include_secrets, profile)


def get_target(target_iqn, include_secrets=False, profile="default"):
    """Return one iSCSI target, redacting CHAP passwords by default.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_iscsi.get_target \\
          iqn.2026-01.com.example:storage
    """
    return _invoke(iscsi_api.get_target, target_iqn, include_secrets, profile)


def create_target(
    target_iqn,
    portals,
    target_controls=None,
    acl_enabled=False,
    auth=None,
    disks=None,
    clients=None,
    groups=None,
    profile="default",
):
    """Create an iSCSI target from structured portal, disk, client, and group data.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_iscsi.create_target \\
          iqn.2026-01.com.example:storage \\
          portals='[{"host":"gateway-a","ip":"192.0.2.10"}]'
    """
    return _invoke(
        iscsi_api.create_target,
        target_iqn,
        portals,
        target_controls,
        acl_enabled,
        auth,
        disks,
        clients,
        groups,
        profile,
    )


def update_target(
    target_iqn,
    portals,
    new_target_iqn=None,
    target_controls=None,
    acl_enabled=False,
    auth=None,
    disks=None,
    clients=None,
    groups=None,
    confirm=False,
    profile="default",
):
    """Replace a target; requires ``confirm=true`` because omissions remove config.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_iscsi.update_target \\
          iqn.2026-01.com.example:storage \\
          portals='[{"host":"gateway-a","ip":"192.0.2.10"}]' confirm=true
    """
    return _invoke(
        iscsi_api.update_target,
        target_iqn,
        portals,
        new_target_iqn,
        target_controls,
        acl_enabled,
        auth,
        disks,
        clients,
        groups,
        confirm,
        profile,
    )


def delete_target(target_iqn, confirm=False, profile="default"):
    """Delete a target and its gateway mappings; requires ``confirm=true``.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_iscsi.delete_target \\
          iqn.2026-01.com.example:storage confirm=true
    """
    return _invoke(iscsi_api.delete_target, target_iqn, confirm, profile)
