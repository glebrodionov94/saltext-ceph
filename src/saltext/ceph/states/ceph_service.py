"""Declaratively manage cephadm ServiceSpec resources."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import service
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_service"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_CORE_SERVICES = frozenset(("mon", "mgr"))
_MISSING = object()


def __virtual__():
    required = {
        "ceph_service.list",
        "ceph_service.get",
        "ceph_service.create",
        "ceph_service.update",
        "ceph_service.delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _exists(name, profile):
    items = reconcile.data(
        __salt__["ceph_service.list"](service_name=name, limit=-1, profile=profile),
        "Ceph service list",
        expected=list,
    )
    return any(isinstance(item, Mapping) and item.get("service_name") == name for item in items)


def _current(name, profile):
    if not _exists(name, profile):
        return None
    value = reconcile.data(__salt__["ceph_service.get"](name, profile=profile), "Ceph service read")
    if not isinstance(value, Mapping) or value.get("service_name") != name:
        raise ProtocolError("Ceph service read returned an unexpected response shape.")
    return dict(value)


def _project_service_spec(current, desired):
    """Project a ServiceSpec while honoring fields Ceph omits at default values."""
    projected = {}
    nested_spec = current.get("spec")
    for key, wanted in desired.items():
        actual = current.get(key, _MISSING)
        # Dashboard's orchestrator read model keeps common ServiceSpec fields
        # at the top level and nests service-specific fields under ``spec``.
        # Mutating endpoints still expect one flat ServiceSpec.
        if actual is _MISSING and key != "spec" and isinstance(nested_spec, Mapping):
            actual = nested_spec.get(key, _MISSING)
        if isinstance(wanted, Mapping) and isinstance(actual, Mapping):
            projected[key] = _project_service_spec(actual, wanted)
        elif isinstance(wanted, Mapping) and actual is _MISSING:
            projected[key] = _project_service_spec({}, wanted)
        elif actual is _MISSING:
            # ServiceSpec.to_json() omits false, zero, null and empty values.
            projected[key] = wanted if not wanted else None
        else:
            projected[key] = actual
    return projected


def present(
    name,
    service_spec,
    profile="default",
    task_timeout=1800.0,
    task_interval=5.0,
):
    """Ensure a cephadm service has the complete declared ServiceSpec."""
    ret = reconcile.state_result(name)
    try:
        name = service.validate_service_name(name)
        desired = service.validate_service_spec(service_spec, name)
        current = _current(name, profile)
        old = None if current is None else _project_service_spec(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"Ceph service {name} is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"Ceph service {name} would be reconciled.")
        operation = "ceph_service.create" if current is None else "ceph_service.update"
        response = __salt__[operation](name, desired, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after_resource = reconcile.wait_for_convergence(
            lambda: _current(name, profile),
            lambda observed: observed is not None
            and _project_service_spec(observed, desired) == desired,
            timeout=task_timeout,
            interval=task_interval,
            timeout_message=f"Ceph service {name} did not converge after mutation.",
        )
        after = _project_service_spec(after_resource, desired)
        return reconcile.changed(ret, old, after, f"Ceph service {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    allow_core=False,
    profile="default",
    task_timeout=1800.0,
    task_interval=5.0,
):
    """Ensure a cephadm service is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = service.validate_service_name(name)
        for label, value in (("confirm", confirm), ("allow_core", allow_core)):
            if not isinstance(value, bool):
                raise ConfigurationError(f"{label} must be a boolean.")
        current = _current(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"Ceph service {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"Ceph service {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting a Ceph service requires confirm=True.")
        if name in _CORE_SERVICES and not allow_core:
            raise ConfigurationError(
                "Deleting mon or mgr requires allow_core=True in addition to confirmation."
            )
        response = __salt__["ceph_service.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        reconcile.wait_for_convergence(
            lambda: _current(name, profile),
            lambda observed: observed is None,
            timeout=task_timeout,
            interval=task_interval,
            timeout_message=f"Ceph service {name} still exists after deletion.",
        )
        return reconcile.changed(ret, current, None, f"Ceph service {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
