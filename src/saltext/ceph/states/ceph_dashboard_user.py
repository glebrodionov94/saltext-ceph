"""Declaratively manage Ceph Dashboard login users."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import dashboard_user
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_dashboard_user"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_dashboard_user.list",
        "ceph_dashboard_user.create",
        "ceph_dashboard_user.update",
        "ceph_dashboard_user.delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _optional_text(value, label):
    if value is not None and (not isinstance(value, str) or len(value) > 4096 or "\x00" in value):
        raise ConfigurationError(f"{label} must be a bounded string or null.")
    return value


def _expiration(value):
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise ConfigurationError("pwd_expiration_date must be a non-negative Unix timestamp.")
    return value


def _desired(
    username,
    display_name,
    email,
    roles,
    enabled,
    pwd_expiration_date,
    pwd_update_required,
):
    if not isinstance(enabled, bool) or not isinstance(pwd_update_required, bool):
        raise ConfigurationError("enabled and pwd_update_required must be booleans.")
    return {
        "username": dashboard_user.validate_username(username),
        "name": _optional_text(display_name, "display_name"),
        "email": _optional_text(email, "email"),
        "roles": sorted(dashboard_user.validate_roles(roles) or []),
        "enabled": enabled,
        "pwdExpirationDate": _expiration(pwd_expiration_date),
        "pwdUpdateRequired": pwd_update_required,
    }


def _view(item):
    if not isinstance(item, Mapping):
        raise ProtocolError("Ceph Dashboard user list returned an unexpected response shape.")
    required = {
        "username",
        "name",
        "email",
        "roles",
        "enabled",
        "pwdExpirationDate",
        "pwdUpdateRequired",
    }
    if not required.issubset(item):
        raise ProtocolError("Ceph Dashboard user list returned an unexpected response shape.")
    try:
        desired = _desired(
            item["username"],
            item["name"],
            item["email"],
            item["roles"],
            item["enabled"],
            item["pwdExpirationDate"],
            item["pwdUpdateRequired"],
        )
    except ConfigurationError as exc:
        raise ProtocolError(
            "Ceph Dashboard user list returned an unexpected response shape."
        ) from exc
    return desired


def _current(username, profile):
    items = reconcile.data(
        __salt__["ceph_dashboard_user.list"](profile=profile),
        "Ceph Dashboard user list",
        expected=list,
    )
    item = next(
        (
            entry
            for entry in items
            if isinstance(entry, Mapping) and entry.get("username") == username
        ),
        None,
    )
    return None if item is None else _view(item)


def _validate_password_source(source):
    if source is None:
        return
    # Read and discard once so test mode validates the same secure file boundary
    # as the execution module without retaining or returning its contents.
    secret_file.read(source)


def present(
    name,
    password_source=None,
    display_name=None,
    email=None,
    roles=None,
    enabled=True,
    pwd_expiration_date=None,
    pwd_update_required=True,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a Dashboard user has the complete declared public fields.

    ``password_source`` is used only when the user must be created. Dashboard
    never returns password hashes and exposes no equality check, so this state
    deliberately does not claim to detect or repair password drift.
    """
    ret = reconcile.state_result(name)
    try:
        desired = _desired(
            name,
            display_name,
            email,
            roles,
            enabled,
            pwd_expiration_date,
            pwd_update_required,
        )
        current = _current(name, profile)
        if current == desired:
            return reconcile.no_change(ret, f"Dashboard user {name} is already current.")
        test_mode = __opts__.get("test", False)
        if current is None and test_mode:
            _validate_password_source(password_source)
        if test_mode:
            return reconcile.planned(
                ret, current, desired, f"Dashboard user {name} would be reconciled."
            )
        if current is None:
            response = __salt__["ceph_dashboard_user.create"](
                name,
                password_source=password_source,
                name=desired["name"],
                email=desired["email"],
                roles=desired["roles"],
                enabled=desired["enabled"],
                pwd_expiration_date=desired["pwdExpirationDate"],
                pwd_update_required=desired["pwdUpdateRequired"],
                profile=profile,
            )
        else:
            response = __salt__["ceph_dashboard_user.update"](
                name,
                password_source=None,
                name=desired["name"],
                email=desired["email"],
                roles=desired["roles"],
                enabled=desired["enabled"],
                pwd_expiration_date=desired["pwdExpirationDate"],
                pwd_update_required=desired["pwdUpdateRequired"],
                profile=profile,
            )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _current(name, profile)
        if after != desired:
            raise ProtocolError(f"Dashboard user {name} did not converge after mutation.")
        return reconcile.changed(ret, current, after, f"Dashboard user {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a Dashboard login user is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = dashboard_user.validate_username(name)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        current = _current(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"Dashboard user {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"Dashboard user {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting a Dashboard user requires confirm=True.")
        response = __salt__["ceph_dashboard_user.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        if _current(name, profile) is not None:
            raise ProtocolError(f"Dashboard user {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"Dashboard user {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
