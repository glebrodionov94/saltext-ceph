"""Declaratively manage erasure-code profiles."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import erasure_code_profile
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_erasure_code_profile"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_erasure_code_profile.list",
        "ceph_erasure_code_profile.create",
        "ceph_erasure_code_profile.delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _find(name, profile):
    items = reconcile.data(
        __salt__["ceph_erasure_code_profile.list"](profile=profile),
        "Ceph erasure-code profile list",
        expected=list,
    )
    item = next(
        (entry for entry in items if isinstance(entry, Mapping) and entry.get("name") == name),
        None,
    )
    return None if item is None else dict(item)


def _view(current, desired):
    if current is None:
        return None
    return {key: current.get(key) for key in desired}


def present(
    name,
    settings=None,
    replace=False,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure an immutable profile exists, optionally replacing drift."""
    ret = reconcile.state_result(name)
    try:
        name = erasure_code_profile.validate_profile_name(name)
        desired = {"name": name, **erasure_code_profile.normalize_settings(settings)}
        for label, value in (("replace", replace), ("confirm", confirm)):
            if not isinstance(value, bool):
                raise ConfigurationError(f"{label} must be a boolean.")
        resource = _find(name, profile)
        current = _view(resource, desired)
        if current == desired:
            return reconcile.no_change(ret, f"Ceph erasure-code profile {name} is already current.")
        if resource is not None and not replace:
            raise ConfigurationError(
                f"Ceph erasure-code profile {name} is immutable and has drift; set replace=True."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                desired,
                f"Ceph erasure-code profile {name} would be reconciled.",
            )
        if resource is not None:
            if not confirm:
                raise ConfigurationError("Replacing an erasure-code profile requires confirm=True.")
            response = __salt__["ceph_erasure_code_profile.delete"](
                name, confirm=True, profile=profile
            )
            reconcile.wait_if_accepted(
                __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
            )
        response = __salt__["ceph_erasure_code_profile.create"](
            name, settings=settings, profile=profile
        )
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        after = _view(_find(name, profile), desired)
        if after != desired:
            raise ProtocolError(f"Ceph erasure-code profile {name} did not converge.")
        return reconcile.changed(
            ret, current, after, f"Ceph erasure-code profile {name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a profile is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = erasure_code_profile.validate_profile_name(name)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        current = _find(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"Ceph erasure-code profile {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                None,
                f"Ceph erasure-code profile {name} would be deleted.",
            )
        if not confirm:
            raise ConfigurationError("Deleting an erasure-code profile requires confirm=True.")
        response = __salt__["ceph_erasure_code_profile.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        if _find(name, profile) is not None:
            raise ProtocolError(f"Ceph erasure-code profile {name} still exists after deletion.")
        return reconcile.changed(
            ret, current, None, f"Ceph erasure-code profile {name} was deleted."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
