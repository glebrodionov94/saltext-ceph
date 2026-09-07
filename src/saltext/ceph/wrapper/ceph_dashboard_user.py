"""Manage Ceph Dashboard login users from the salt-ssh controller."""

from saltext.ceph.utils.ceph import dashboard_user_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_dashboard_user"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(profile="default"):
    """List Dashboard login users."""
    return _invoke(dashboard_user_api.list_, profile)


def get(username, profile="default"):
    """Return one Dashboard login user."""
    return _invoke(dashboard_user_api.get, username, profile)


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
    """Create a Dashboard login user."""
    return _invoke(
        dashboard_user_api.create,
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
    """Replace a Dashboard user's mutable fields."""
    return _invoke(
        dashboard_user_api.update,
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
    """Delete a Dashboard login user after explicit confirmation."""
    return _invoke(dashboard_user_api.delete, username, confirm, profile)


def validate_password(
    password_source,
    username=None,
    old_password_source=None,
    profile="default",
):
    """Validate a file-sourced password against Dashboard policy."""
    return _invoke(
        dashboard_user_api.validate_password,
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
    """Change the authenticated user's password from controller-local files."""
    return _invoke(
        dashboard_user_api.change_password,
        username,
        old_password_source,
        new_password_source,
        profile,
    )
