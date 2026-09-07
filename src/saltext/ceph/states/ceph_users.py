"""Declaratively manage CephX users."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import users
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_users"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_users.get",
        "ceph_users.create",
        "ceph_users.update",
        "ceph_users.delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _caps(value):
    if isinstance(value, Mapping):
        value = [{"entity": key, "cap": cap} for key, cap in value.items()]
    return sorted(users.validate_capabilities(value), key=lambda item: item["entity"])


def _current(name, profile):
    value = reconcile.data(__salt__["ceph_users.get"](name, profile=profile), "CephX user read")
    if value is None:
        return None
    if not isinstance(value, Mapping) or value.get("entity") != name:
        raise ProtocolError("CephX user read returned an unexpected response shape.")
    return {"entity": name, "capabilities": _caps(value.get("caps"))}


def present(
    name,
    capabilities,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a CephX entity exists with exactly the declared capabilities."""
    ret = reconcile.state_result(name)
    try:
        desired = {"entity": users.validate_entity(name), "capabilities": _caps(capabilities)}
        current = _current(name, profile)
        if current == desired:
            return reconcile.no_change(ret, f"CephX user {name} is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"CephX user {name} would be reconciled."
            )
        if current is None:
            response = __salt__["ceph_users.create"](name, desired["capabilities"], profile=profile)
        else:
            response = __salt__["ceph_users.update"](name, desired["capabilities"], profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _current(name, profile)
        if after != desired:
            raise ProtocolError(f"CephX user {name} did not converge after mutation.")
        return reconcile.changed(ret, current, after, f"CephX user {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a CephX entity is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        users.validate_entity(name)
        if not isinstance(confirm, bool):
            raise CephError("confirm must be a boolean.")
        current = _current(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"CephX user {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"CephX user {name} would be deleted.")
        if not confirm:
            raise CephError("Deleting a CephX user requires confirm=True.")
        response = __salt__["ceph_users.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        if _current(name, profile) is not None:
            raise ProtocolError(f"CephX user {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"CephX user {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
