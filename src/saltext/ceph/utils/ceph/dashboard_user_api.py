"""Salt-facing composition for Dashboard login-user operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import dashboard_user
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import ConfigurationError


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def _password(source):
    value = secret_file.read(source).rstrip("\r\n")
    if not value:
        raise ConfigurationError("Password file contains only line separators.")
    return value


def list_(opts, pillar, context, profile="default"):
    """List Dashboard login users."""
    return dashboard_user.list_(_client(opts, pillar, context, profile)).as_dict()


def get(opts, pillar, context, username, profile="default"):
    """Return one Dashboard login user."""
    return dashboard_user.get(_client(opts, pillar, context, profile), username).as_dict()


def create(
    opts,
    pillar,
    context,
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
    """Create a Dashboard login user, reading an optional password file."""
    password = _password(password_source) if password_source is not None else None
    return dashboard_user.create(
        _client(opts, pillar, context, profile),
        username,
        password,
        name,
        email,
        roles,
        enabled,
        pwd_expiration_date,
        pwd_update_required,
    ).as_dict()


def update(
    opts,
    pillar,
    context,
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
    """Replace a Dashboard user's mutable fields, optionally reading a password file."""
    password = _password(password_source) if password_source is not None else None
    return dashboard_user.update(
        _client(opts, pillar, context, profile),
        username,
        password,
        name,
        email,
        roles,
        enabled,
        pwd_expiration_date,
        pwd_update_required,
    ).as_dict()


def delete(opts, pillar, context, username, confirm=False, profile="default"):
    """Delete a Dashboard login user after explicit confirmation."""
    return dashboard_user.delete(
        _client(opts, pillar, context, profile), username, confirm
    ).as_dict()


def validate_password(
    opts,
    pillar,
    context,
    password_source,
    username=None,
    old_password_source=None,
    profile="default",
):
    """Validate a file-sourced password against Dashboard policy."""
    old_password = _password(old_password_source) if old_password_source is not None else None
    return dashboard_user.validate_password_policy(
        _client(opts, pillar, context, profile),
        _password(password_source),
        username,
        old_password,
    ).as_dict()


def change_password(
    opts,
    pillar,
    context,
    username,
    old_password_source,
    new_password_source,
    profile="default",
):
    """Change the authenticated user's password from two local files."""
    return dashboard_user.change_password(
        _client(opts, pillar, context, profile),
        username,
        _password(old_password_source),
        _password(new_password_source),
    ).as_dict()
