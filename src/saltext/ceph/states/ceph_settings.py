"""Declaratively manage non-secret Ceph Dashboard settings."""

import json
from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import settings
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_settings"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_SENSITIVE_WORDS = ("PASSWORD", "SECRET", "TOKEN", "KEY")


def __virtual__():
    required = {
        "ceph_settings.get",
        "ceph_settings.set",
        "ceph_settings.delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _contains_sensitive_key(value):
    if isinstance(value, Mapping):
        return any(
            (isinstance(key, str) and any(word in key.upper() for word in _SENSITIVE_WORDS))
            or _contains_sensitive_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _canonical(value, *, response=False):
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        if response:
            raise ProtocolError("Ceph Dashboard setting returned an invalid JSON value.") from exc
        raise ConfigurationError("setting value must be JSON-serializable.") from exc


def _same(first, second):
    return _canonical(first, response=True) == _canonical(second, response=True)


def _managed_name(name):
    name = settings.normalize_name(name)
    if settings.is_secret(name):
        raise ConfigurationError(
            "Credential-like Dashboard settings cannot be reconciled because the API "
            "redacts their current values; rotate them explicitly with ceph_settings.set."
        )
    return name


def _current(name, profile):
    item = reconcile.data(
        __salt__["ceph_settings.get"](name, profile=profile),
        "Ceph Dashboard setting read",
        expected=Mapping,
    )
    required = {"name", "default", "type", "value"}
    if not required.issubset(item) or not isinstance(item["type"], str):
        raise ProtocolError("Ceph Dashboard setting returned an unexpected response shape.")
    try:
        response_name = settings.normalize_name(item["name"])
    except ConfigurationError as exc:
        raise ProtocolError(
            "Ceph Dashboard setting returned an unexpected response shape."
        ) from exc
    if response_name != name:
        raise ProtocolError("Ceph Dashboard setting response did not match the requested name.")
    if (
        item.get("redacted")
        or _contains_sensitive_key(item["value"])
        or _contains_sensitive_key(item["default"])
    ):
        raise ConfigurationError(
            "Dashboard redacted part of this setting, so exact reconciliation is unavailable."
        )
    _canonical(item["value"], response=True)
    _canonical(item["default"], response=True)
    return {"name": name, "value": item["value"], "default": item["default"]}


def managed(
    name,
    value,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a non-secret Dashboard setting has exactly ``value``."""
    ret = reconcile.state_result(name)
    try:
        name = _managed_name(name)
        desired = settings.normalize_values({name: value})[name]
        if _contains_sensitive_key(desired):
            raise ConfigurationError(
                "Structured values with credential-like keys cannot be emitted in state changes."
            )
        _canonical(desired)
        current = _current(name, profile)
        if _same(current["value"], desired):
            return reconcile.no_change(ret, f"Dashboard setting {name} is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current["value"],
                desired,
                f"Dashboard setting {name} would be updated.",
            )
        response = __salt__["ceph_settings.set"](name, value=desired, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _current(name, profile)
        if not _same(after["value"], desired):
            raise ProtocolError(f"Dashboard setting {name} did not converge after mutation.")
        return reconcile.changed(
            ret, current["value"], after["value"], f"Dashboard setting {name} was updated."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def default(
    name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Reset a non-secret Dashboard setting; live reset requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = _managed_name(name)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        current = _current(name, profile)
        if _same(current["value"], current["default"]):
            return reconcile.no_change(ret, f"Dashboard setting {name} is already at its default.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current["value"],
                current["default"],
                f"Dashboard setting {name} would be reset.",
            )
        if not confirm:
            raise ConfigurationError("Resetting a Dashboard setting requires confirm=True.")
        response = __salt__["ceph_settings.delete"](name, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _current(name, profile)
        if not _same(after["value"], after["default"]):
            raise ProtocolError(f"Dashboard setting {name} did not reset to its default.")
        return reconcile.changed(
            ret,
            current["value"],
            after["value"],
            f"Dashboard setting {name} was reset.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
