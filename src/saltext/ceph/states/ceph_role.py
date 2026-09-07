"""Declaratively manage Ceph Dashboard authorization roles."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import role
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_role"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_role.list",
        "ceph_role.create",
        "ceph_role.update",
        "ceph_role.delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _permissions(value, *, response=False):
    try:
        normalized = role.validate_scopes_permissions(value) or {}
    except ConfigurationError as exc:
        if response:
            raise ProtocolError("Ceph Dashboard role returned invalid permissions.") from exc
        raise
    return {scope: sorted(permissions) for scope, permissions in normalized.items() if permissions}


def _desired(name, description, scopes_permissions):
    return {
        "name": role.validate_name(name),
        "description": role.validate_description(description),
        "scopes_permissions": _permissions(scopes_permissions),
    }


def _view(item):
    required = {"name", "description", "scopes_permissions", "system"}
    if (
        not isinstance(item, Mapping)
        or not required.issubset(item)
        or not isinstance(item.get("system"), bool)
    ):
        raise ProtocolError("Ceph Dashboard role list returned an unexpected response shape.")
    try:
        name = role.validate_name(item.get("name"))
        description = role.validate_description(item.get("description"))
    except ConfigurationError as exc:
        raise ProtocolError(
            "Ceph Dashboard role list returned an unexpected response shape."
        ) from exc
    return {
        "name": name,
        "description": description,
        "scopes_permissions": _permissions(item.get("scopes_permissions"), response=True),
        "system": item["system"],
    }


def _current(name, profile):
    items = reconcile.data(
        __salt__["ceph_role.list"](profile=profile),
        "Ceph Dashboard role list",
        expected=list,
    )
    item = next(
        (entry for entry in items if isinstance(entry, Mapping) and entry.get("name") == name),
        None,
    )
    return None if item is None else _view(item)


def _managed_view(current):
    if current is None:
        return None
    return {key: current[key] for key in ("name", "description", "scopes_permissions")}


def present(
    name,
    description=None,
    scopes_permissions=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a custom role has exactly the declared description and permissions."""
    ret = reconcile.state_result(name)
    try:
        desired = _desired(name, description, scopes_permissions)
        resource = _current(desired["name"], profile)
        current = _managed_view(resource)
        if current == desired:
            return reconcile.no_change(ret, f"Dashboard role {name} is already current.")
        if resource is not None and resource["system"]:
            raise ConfigurationError("Built-in Dashboard roles cannot be updated.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"Dashboard role {name} would be reconciled."
            )
        if resource is None:
            response = __salt__["ceph_role.create"](
                name,
                description=desired["description"],
                scopes_permissions=desired["scopes_permissions"],
                profile=profile,
            )
        else:
            response = __salt__["ceph_role.update"](
                name,
                description=desired["description"],
                scopes_permissions=desired["scopes_permissions"],
                profile=profile,
            )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _managed_view(_current(name, profile))
        if after != desired:
            raise ProtocolError(f"Dashboard role {name} did not converge after mutation.")
        return reconcile.changed(ret, current, after, f"Dashboard role {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a custom role is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = role.validate_name(name)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        resource = _current(name, profile)
        if resource is None:
            return reconcile.no_change(ret, f"Dashboard role {name} is already absent.")
        if resource["system"]:
            raise ConfigurationError("Built-in Dashboard roles cannot be deleted.")
        current = _managed_view(resource)
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"Dashboard role {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting a Dashboard role requires confirm=True.")
        response = __salt__["ceph_role.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        if _current(name, profile) is not None:
            raise ProtocolError(f"Dashboard role {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"Dashboard role {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
