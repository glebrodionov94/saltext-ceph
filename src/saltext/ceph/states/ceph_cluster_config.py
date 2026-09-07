"""Declaratively manage Ceph monitor configuration values."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import cluster_configuration
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_cluster_config"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_cluster_config.list",
        "ceph_cluster_config.set",
        "ceph_cluster_config.remove",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _section_values(item):
    if item is None:
        return {}
    if not isinstance(item, Mapping) or not isinstance(item.get("value", []), list):
        raise ProtocolError("Ceph configuration read returned an unexpected response shape.")
    result = {}
    for entry in item.get("value", []):
        if not isinstance(entry, Mapping) or not isinstance(entry.get("section"), str):
            raise ProtocolError("Ceph configuration read returned an unexpected response shape.")
        result[entry["section"]] = entry.get("value")
    return result


def _current(name, profile):
    items = reconcile.data(
        __salt__["ceph_cluster_config.list"](profile=profile),
        "Ceph configuration list",
        expected=list,
    )
    item = next(
        (entry for entry in items if isinstance(entry, Mapping) and entry.get("name") == name),
        None,
    )
    return _section_values(item)


def _effective(values):
    return {
        entry["section"]: entry["value"] for entry in values if entry["value"] not in (None, "")
    }


def _managed_view(current, desired, replace, declared=None):
    if replace:
        return dict(current)
    declared = set(desired) if declared is None else declared
    return {section: current[section] for section in declared if section in current}


def managed(
    name,
    values,
    force_update=None,
    replace=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Manage declared section values, optionally removing every undeclared value.

    A desired ``null`` or empty string removes that section. With ``replace=false``
    undeclared sections remain unmanaged; ``replace=true`` makes the declaration
    the complete explicit value set for this option.
    """
    ret = reconcile.state_result(name)
    try:
        name = cluster_configuration.validate_name(name)
        desired_entries = cluster_configuration.validate_values(values)
        if force_update is not None and not isinstance(force_update, bool):
            raise CephError("force_update must be a boolean or null.")
        if not isinstance(replace, bool):
            raise CephError("replace must be a boolean.")
        desired = _effective(desired_entries)
        declared = {entry["section"] for entry in desired_entries}
        current = _current(name, profile)
        old = _managed_view(current, desired, replace, declared)
        if old == desired:
            return reconcile.no_change(ret, f"Ceph configuration option {name} is already current.")

        updates = list(desired_entries)
        if replace:
            updates.extend(
                {"section": section, "value": None}
                for section in current
                if section not in declared
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                old,
                desired,
                f"Ceph configuration option {name} would be reconciled.",
            )
        response = __salt__["ceph_cluster_config.set"](
            name, updates, force_update=force_update, profile=profile
        )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after_all = _current(name, profile)
        after = _managed_view(after_all, desired, replace, declared)
        if after != desired:
            raise ProtocolError(f"Ceph configuration option {name} did not converge.")
        return reconcile.changed(
            ret, old, after, f"Ceph configuration option {name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    section,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure one option has no explicit value in a section."""
    ret = reconcile.state_result(name)
    try:
        name = cluster_configuration.validate_name(name)
        section = cluster_configuration.validate_section(section)
        current = _current(name, profile)
        if section not in current:
            return reconcile.no_change(ret, f"Ceph configuration {name} has no value in {section}.")
        old = {section: current[section]}
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, {}, f"Ceph configuration {name}[{section}] would be removed."
            )
        response = __salt__["ceph_cluster_config.remove"](name, section, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        if section in _current(name, profile):
            raise ProtocolError(f"Ceph configuration {name}[{section}] still exists.")
        return reconcile.changed(ret, old, {}, f"Ceph configuration {name}[{section}] was removed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
