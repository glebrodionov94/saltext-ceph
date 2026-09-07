"""Declaratively manage CRUSH placement rules."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import crush_rule
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_crush_rule"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_TYPE_NAMES = {1: "replication", 3: "erasure"}


def __virtual__():
    required = {
        "ceph_crush_rule.list",
        "ceph_crush_rule.create",
        "ceph_crush_rule.delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _find(name, profile):
    items = reconcile.data(
        __salt__["ceph_crush_rule.list"](profile=profile),
        "Ceph CRUSH rule list",
        expected=list,
    )
    item = next(
        (entry for entry in items if isinstance(entry, Mapping) and entry.get("rule_name") == name),
        None,
    )
    return None if item is None else dict(item)


def _describe(item):
    if item is None:
        return None
    steps = item.get("steps")
    if not isinstance(steps, list) or not all(isinstance(step, Mapping) for step in steps):
        raise ProtocolError("Ceph CRUSH rule steps have an unexpected shape.")
    take = next((step for step in steps if step.get("op") == "take"), None)
    choose = next((step for step in steps if str(step.get("op", "")).startswith("choose")), None)
    if take is None or choose is None or not isinstance(take.get("item_name"), str):
        raise ProtocolError("Ceph CRUSH rule cannot be compared declaratively.")
    root, separator, device_class = take["item_name"].partition("~")
    rule_type = item.get("type", item.get("pool_type"))
    rule_type = _TYPE_NAMES.get(rule_type, rule_type)
    return {
        "name": item.get("rule_name"),
        "failure_domain": choose.get("type"),
        "device_class": device_class if separator else None,
        "root": root if rule_type == "replication" else None,
        "pool_type": rule_type,
    }


def _desired(payload):
    return {
        "name": payload["name"],
        "failure_domain": payload["failure_domain"],
        "device_class": payload.get("device_class"),
        "root": payload.get("root"),
        "pool_type": payload.get("pool_type", "replication"),
    }


def present(
    name,
    failure_domain,
    device_class=None,
    root=None,
    erasure_profile=None,
    pool_type="replication",
    replace=False,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a rule exists; immutable drift can be replaced explicitly."""
    ret = reconcile.state_result(name)
    try:
        payload = crush_rule.build_create_payload(
            name, failure_domain, device_class, root, erasure_profile, pool_type
        )
        desired = _desired(payload)
        for label, value in (("replace", replace), ("confirm", confirm)):
            if not isinstance(value, bool):
                raise ConfigurationError(f"{label} must be a boolean.")
        resource = _find(name, profile)
        current = _describe(resource)
        if current == desired:
            return reconcile.no_change(ret, f"Ceph CRUSH rule {name} is already current.")
        if resource is not None and not replace:
            raise ConfigurationError(
                f"Ceph CRUSH rule {name} is immutable and has drift; set replace=True."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"Ceph CRUSH rule {name} would be reconciled."
            )
        if resource is not None:
            if not confirm:
                raise ConfigurationError("Replacing a CRUSH rule requires confirm=True.")
            response = __salt__["ceph_crush_rule.delete"](name, confirm=True, profile=profile)
            reconcile.wait_if_accepted(
                __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
            )
        response = __salt__["ceph_crush_rule.create"](
            name,
            failure_domain,
            device_class=device_class,
            root=root,
            erasure_profile=erasure_profile,
            pool_type=pool_type,
            profile=profile,
        )
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        after = _describe(_find(name, profile))
        if after != desired:
            raise ProtocolError(f"Ceph CRUSH rule {name} did not converge.")
        return reconcile.changed(ret, current, after, f"Ceph CRUSH rule {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a CRUSH rule is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = crush_rule.validate_rule_name(name, "name")
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        current = _find(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"Ceph CRUSH rule {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"Ceph CRUSH rule {name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting a CRUSH rule requires confirm=True.")
        response = __salt__["ceph_crush_rule.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        if _find(name, profile) is not None:
            raise ProtocolError(f"Ceph CRUSH rule {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"Ceph CRUSH rule {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
