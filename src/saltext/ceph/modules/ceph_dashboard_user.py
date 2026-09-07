"""Manage Ceph Dashboard login users through the Dashboard REST API."""

from saltext.ceph.utils.ceph import dashboard_user_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_dashboard_user"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(profile="default"):
    """List Dashboard login users without password material.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_dashboard_user.list
    """
    return salt_adapter.invoke(dashboard_user_api.list_, __opts__, __pillar__, __context__, profile)


def get(username, profile="default"):
    """Return one Dashboard login user.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_dashboard_user.get operator
    """
    return salt_adapter.invoke(
        dashboard_user_api.get, __opts__, __pillar__, __context__, username, profile
    )


def create(
    username,
    password_source=None,
    name=None,
    email=None,
    roles=None,
    enabled=True,
    pwd_expiration_date=None,
    pwd_update_required=True,
    profile="default",
):
    """Create a Dashboard user, reading its password from an optional file.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_dashboard_user.create operator \\
          password_source=/run/secrets/operator-password roles='["read-only"]'
    """
    return salt_adapter.invoke(
        dashboard_user_api.create,
        __opts__,
        __pillar__,
        __context__,
        username,
        password_source,
        name,
        email,
        roles,
        enabled,
        pwd_expiration_date,
        pwd_update_required,
        profile,
    )


def update(
    username,
    password_source=None,
    name=None,
    email=None,
    roles=None,
    enabled=None,
    pwd_expiration_date=None,
    pwd_update_required=False,
    profile="default",
):
    """Replace a Dashboard user's mutable fields and optional password.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_dashboard_user.update operator \\
          name='Storage operator' roles='["read-only"]' enabled=true
    """
    return salt_adapter.invoke(
        dashboard_user_api.update,
        __opts__,
        __pillar__,
        __context__,
        username,
        password_source,
        name,
        email,
        roles,
        enabled,
        pwd_expiration_date,
        pwd_update_required,
        profile,
    )


def delete(username, confirm=False, profile="default"):
    """Delete a Dashboard login user after explicit confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_dashboard_user.delete operator confirm=true
    """
    return salt_adapter.invoke(
        dashboard_user_api.delete,
        __opts__,
        __pillar__,
        __context__,
        username,
        confirm,
        profile,
    )


def validate_password(
    password_source,
    username=None,
    old_password_source=None,
    profile="default",
):
    """Validate a file-sourced password against Dashboard policy.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_dashboard_user.validate_password \\
          /run/secrets/proposed-password username=operator
    """
    return salt_adapter.invoke(
        dashboard_user_api.validate_password,
        __opts__,
        __pillar__,
        __context__,
        password_source,
        username,
        old_password_source,
        profile,
    )


def change_password(
    username,
    old_password_source,
    new_password_source,
    profile="default",
):
    """Change the authenticated user's password using two local files.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_dashboard_user.change_password operator \\
          /run/secrets/old-password /run/secrets/new-password
    """
    return salt_adapter.invoke(
        dashboard_user_api.change_password,
        __opts__,
        __pillar__,
        __context__,
        username,
        old_password_source,
        new_password_source,
        profile,
    )
