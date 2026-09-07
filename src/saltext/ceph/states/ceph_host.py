"""Declaratively manage cephadm hosts."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import host
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_host"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_host.list",
        "ceph_host.create",
        "ceph_host.delete",
        "ceph_host.drain",
        "ceph_host.set_labels",
        "ceph_host.toggle_maintenance",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _find(name, profile, include_service_instances=False):
    items = reconcile.data(
        __salt__["ceph_host.list"](
            sources=["orchestrator"],
            facts=False,
            limit=-1,
            include_service_instances=include_service_instances,
            profile=profile,
        ),
        "Ceph host list",
        expected=list,
    )
    item = next(
        (entry for entry in items if isinstance(entry, Mapping) and entry.get("hostname") == name),
        None,
    )
    if item is None:
        return None
    labels = item.get("labels")
    if labels is None:
        labels = []
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise ProtocolError("Ceph host list returned an unexpected response shape.")
    address = item.get("addr")
    if address in (None, ""):
        address = name
    if not isinstance(address, str):
        raise ProtocolError("Ceph host list returned an unexpected response shape.")
    status = item.get("status")
    if status is None:
        status = ""
    if not isinstance(status, str):
        raise ProtocolError("Ceph host list returned an unexpected response shape.")
    result = {
        "hostname": name,
        "address": address,
        "labels": sorted(labels),
        "maintenance": status == "maintenance",
    }
    if include_service_instances:
        instances = item.get("service_instances")
        if not isinstance(instances, list):
            raise ProtocolError("Ceph host list omitted requested service instance data.")
        normalized = []
        for instance in instances:
            if (
                not isinstance(instance, Mapping)
                or not isinstance(instance.get("type"), str)
                or isinstance(instance.get("count"), bool)
                or not isinstance(instance.get("count"), int)
                or instance["count"] < 0
            ):
                raise ProtocolError("Ceph host list returned invalid service instance data.")
            normalized.append({"type": instance["type"], "count": instance["count"]})
        result["service_instances"] = sorted(normalized, key=lambda value: value["type"])
    return result


def _desired(name, address, labels, maintenance):
    desired = {"hostname": host.validate_hostname(name)}
    if address is not None:
        desired["address"] = host.validate_optional_text(address, "address")
    if labels is not None:
        desired["labels"] = sorted(host.validate_labels(labels, optional=False))
    if maintenance is not None:
        if not isinstance(maintenance, bool):
            raise ConfigurationError("maintenance must be a boolean or null.")
        desired["maintenance"] = maintenance
    return desired


def _view(current, desired):
    if current is None:
        return None
    return {key: current.get(key) for key in desired}


def present(
    name,
    address=None,
    labels=None,
    maintenance=None,
    force_maintenance=False,
    profile="default",
    task_timeout=900.0,
    task_interval=2.0,
):
    """Ensure a host exists and reconcile its labels and maintenance status.

    Dashboard cannot change the address of an existing host. An address mismatch
    therefore fails without deleting the host.
    """
    ret = reconcile.state_result(name)
    try:
        desired = _desired(name, address, labels, maintenance)
        if not isinstance(force_maintenance, bool):
            raise ConfigurationError("force_maintenance must be a boolean.")
        current = _find(name, profile)
        old = _view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"Ceph host {name} is already current.")
        if current is not None and "address" in desired and old["address"] != desired["address"]:
            raise ConfigurationError(
                "Dashboard cannot update an existing host address; migrate it explicitly."
            )
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"Ceph host {name} would be reconciled.")

        if current is None:
            response = __salt__["ceph_host.create"](
                name,
                address=address,
                labels=desired.get("labels"),
                maintenance=desired.get("maintenance", False),
                profile=profile,
            )
            reconcile.wait_if_accepted(
                __salt__,
                response,
                profile=profile,
                timeout=task_timeout,
                interval=task_interval,
            )
            current = reconcile.wait_for_convergence(
                lambda: _find(name, profile),
                lambda observed: _view(observed, desired) == desired,
                timeout=task_timeout,
                interval=task_interval,
                timeout_message=(
                    f"Ceph host {name} was not visible with its declared fields after creation."
                ),
            )

        if "labels" in desired and current["labels"] != desired["labels"]:
            response = __salt__["ceph_host.set_labels"](name, desired["labels"], profile=profile)
            reconcile.wait_if_accepted(
                __salt__,
                response,
                profile=profile,
                timeout=task_timeout,
                interval=task_interval,
            )
            current = _find(name, profile)
        if (
            "maintenance" in desired
            and current is not None
            and current["maintenance"] != desired["maintenance"]
        ):
            response = __salt__["ceph_host.toggle_maintenance"](
                name, force=force_maintenance, profile=profile
            )
            reconcile.wait_if_accepted(
                __salt__,
                response,
                profile=profile,
                timeout=task_timeout,
                interval=task_interval,
            )

        after_resource = reconcile.wait_for_convergence(
            lambda: _find(name, profile),
            lambda observed: _view(observed, desired) == desired,
            timeout=task_timeout,
            interval=task_interval,
            timeout_message=f"Ceph host {name} did not converge after mutation.",
        )
        after = _view(after_resource, desired)
        return reconcile.changed(ret, old, after, f"Ceph host {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=1800.0,
    task_interval=5.0,
    drain=False,
):
    """Ensure an orchestrator host is absent; live deletion requires confirmation.

    Set ``drain=True`` to schedule daemon removal and wait until Dashboard
    reports no service instances on the host before deleting it.
    """
    ret = reconcile.state_result(name)
    try:
        name = host.validate_hostname(name)
        for label, value in (("confirm", confirm), ("drain", drain)):
            if not isinstance(value, bool):
                raise ConfigurationError(f"{label} must be a boolean.")
        current = _find(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"Ceph host {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"Ceph host {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting a Ceph host requires confirm=True.")
        if drain:
            response = __salt__["ceph_host.drain"](name, profile=profile)
            reconcile.wait_if_accepted(
                __salt__,
                response,
                profile=profile,
                timeout=task_timeout,
                interval=task_interval,
            )
            ready = reconcile.wait_for_convergence(
                lambda: _find(name, profile, include_service_instances=True),
                lambda observed: observed is None
                or not any(instance["count"] for instance in observed["service_instances"]),
                timeout=task_timeout,
                interval=task_interval,
                timeout_message=f"Ceph host {name} still has service instances after draining.",
            )
            if ready is None:
                return reconcile.changed(
                    ret,
                    current,
                    None,
                    f"Ceph host {name} disappeared while draining.",
                )
        response = __salt__["ceph_host.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        reconcile.wait_for_convergence(
            lambda: _find(name, profile),
            lambda observed: observed is None,
            timeout=task_timeout,
            interval=task_interval,
            timeout_message=f"Ceph host {name} still exists after deletion.",
        )
        return reconcile.changed(ret, current, None, f"Ceph host {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
