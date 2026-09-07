"""Declaratively manage stable OSD properties and guarded removal."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import osd
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import APIError
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_osd"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_NON_REMOVABLE_FLAGS = frozenset(
    ("recovery_deletes", "sortbitwise", "pglog_hardlimit", "purged_snapshots")
)


def __virtual__():
    required = {
        "ceph_osd.list",
        "ceph_osd.set_device_class",
        "ceph_osd.safe_to_delete",
        "ceph_osd.remove",
        "ceph_osd.flags",
        "ceph_osd.set_flags",
        "ceph_osd.individual_flags",
        "ceph_osd.set_individual_flags",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _items(profile):
    return reconcile.data(
        __salt__["ceph_osd.list"](limit=-1, profile=profile),
        "Ceph OSD list",
        expected=list,
    )


def _find(svc_id, profile):
    svc_id = osd.normalize_osd_id(svc_id)
    for item in _items(profile):
        if not isinstance(item, Mapping):
            raise ProtocolError("Ceph OSD list returned an unexpected response shape.")
        item_id = item.get("id", item.get("osd"))
        if item_id == svc_id:
            return dict(item)
    return None


def _individual_items(profile):
    """Return the raw OSD-map IDs exposed by the individual-flags endpoint."""
    values = reconcile.data(
        __salt__["ceph_osd.individual_flags"](profile=profile),
        "Ceph individual OSD flags",
        expected=list,
    )
    items = []
    for item in values:
        if (
            not isinstance(item, Mapping)
            or isinstance(item.get("osd"), bool)
            or not isinstance(item.get("osd"), int)
            or not isinstance(item.get("flags"), list)
            or not all(isinstance(flag, str) for flag in item["flags"])
        ):
            raise ProtocolError("Ceph individual OSD flags have an unexpected shape.")
        items.append({"osd": item["osd"], "flags": list(item["flags"])})
    return items


def _removal_status(svc_id, profile):
    """Return OSD-map presence without querying Dashboard's removal queue.

    Ceph 20.2.4 serializes removal entries as mappings, but its detailed OSD
    controllers still access them as objects. The individual-flags endpoint
    reads the same monitor OSD map directly and remains usable during removal.
    """
    for item in _individual_items(profile):
        if item["osd"] == svc_id:
            return {"id": item["osd"], "state": item["flags"]}
    return None


def _find_for_removal(svc_id, profile):
    """Read details and verify apparent absence against the raw OSD map."""
    try:
        current = _find(svc_id, profile)
    except _ERRORS as list_error:
        try:
            current = _removal_status(svc_id, profile)
        except _ERRORS as presence_error:
            raise ProtocolError(
                "Ceph OSD presence could not be read from either Dashboard endpoint. "
                f"The OSD list reported {list_error.__class__.__name__}: {list_error}; "
                "the individual-flags endpoint reported "
                f"{presence_error.__class__.__name__}: {presence_error}"
            ) from presence_error
        return current
    if current is not None:
        return current
    return _removal_status(svc_id, profile)


def _is_destroyed(item):
    states = item.get("state") if isinstance(item, Mapping) else None
    return isinstance(states, list) and "destroyed" in states


def _definitive_removal_rejection(exc):
    """Return whether an exception proves the removal request was not accepted."""
    if isinstance(exc, (ConfigurationError, SaltInvocationError)):
        return True
    if isinstance(exc, APIError):
        status = exc.status
    else:
        info = getattr(exc, "info", None)
        status = info.get("status") if isinstance(info, Mapping) else None
    return not isinstance(status, bool) and isinstance(status, int) and 400 <= status < 500


def _wait_for_absence(svc_id, profile, preserve_id, timeout, interval):
    """Poll the raw OSD map until removal converges despite Dashboard task errors."""
    read_failed = object()
    last_read_error = None

    def _read():
        nonlocal last_read_error
        try:
            observed = _removal_status(svc_id, profile)
        except _ERRORS as exc:
            last_read_error = exc
            return read_failed
        last_read_error = None
        return observed

    try:
        return reconcile.wait_for_convergence(
            _read,
            lambda observed: observed is None or (preserve_id and _is_destroyed(observed)),
            timeout=timeout,
            interval=interval,
            timeout_message=f"OSD {svc_id} absence was not confirmed before timeout.",
        )
    except ProtocolError as timeout_error:
        if last_read_error is not None:
            raise ProtocolError(
                f"{timeout_error} Last post-mutation read reported "
                f"{last_read_error.__class__.__name__}: {last_read_error}"
            ) from last_read_error
        if preserve_id:
            raise ProtocolError(
                f"OSD {svc_id} still exists and is not marked destroyed after removal."
            ) from timeout_error
        raise ProtocolError(f"OSD {svc_id} still exists after removal.") from timeout_error


def _device_class(item):
    if item is None:
        return None
    value = item.get("device_class")
    if value is None and isinstance(item.get("tree"), Mapping):
        value = item["tree"].get("device_class")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProtocolError("Ceph OSD device class has an unexpected response shape.")
    return value


def device_class_managed(
    name,
    device_class,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure one OSD has the declared CRUSH device class."""
    ret = reconcile.state_result(name)
    try:
        svc_id = osd.normalize_osd_id(name)
        if (
            not isinstance(device_class, str)
            or len(device_class) > 64
            or not osd._DEVICE_CLASS_PATTERN.fullmatch(
                device_class
            )  # pylint: disable=protected-access
        ):
            raise ConfigurationError("device_class contains unsupported characters.")
        item = _find(svc_id, profile)
        if item is None:
            raise ConfigurationError(f"OSD {svc_id} does not exist.")
        current = _device_class(item)
        if current == device_class:
            return reconcile.no_change(ret, f"OSD {svc_id} device class is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, device_class, f"OSD {svc_id} device class would be changed."
            )
        response = __salt__["ceph_osd.set_device_class"](svc_id, device_class, profile=profile)
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        after = _device_class(_find(svc_id, profile))
        if after != device_class:
            raise ProtocolError(f"OSD {svc_id} device class did not converge.")
        return reconcile.changed(ret, current, after, f"OSD {svc_id} device class was changed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def flags_managed(
    name,
    flags,
    preserve_required=True,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Manage the complete mutable cluster-wide OSD flag set.

    Ceph's non-removable flags are retained by default because Dashboard's bulk
    replacement endpoint cannot unset them.
    """
    ret = reconcile.state_result(name)
    try:
        desired = set(osd.normalize_cluster_flags(flags))
        if not isinstance(preserve_required, bool):
            raise ConfigurationError("preserve_required must be a boolean.")
        current_value = reconcile.data(
            __salt__["ceph_osd.flags"](profile=profile),
            "Ceph OSD flags",
            expected=list,
        )
        if not all(isinstance(flag, str) for flag in current_value):
            raise ProtocolError("Ceph OSD flags returned an unexpected response shape.")
        current = set(current_value)
        if "purged_snapshots" in desired and "purged_snapshots" not in current:
            raise ConfigurationError("Ceph cannot set the purged_snapshots flag.")
        if preserve_required:
            desired.update(current.intersection(_NON_REMOVABLE_FLAGS))
        old = sorted(current)
        wanted = sorted(desired)
        if old == wanted:
            return reconcile.no_change(ret, "Cluster-wide OSD flags are already current.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, wanted, "Cluster-wide OSD flags would change.")
        response = __salt__["ceph_osd.set_flags"](wanted, profile=profile)
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        after = sorted(
            reconcile.data(
                __salt__["ceph_osd.flags"](profile=profile),
                "Ceph OSD flags",
                expected=list,
            )
        )
        if after != wanted:
            raise ProtocolError("Cluster-wide OSD flags did not converge.")
        return reconcile.changed(ret, old, after, "Cluster-wide OSD flags were changed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _individual_current(ids, desired, profile):
    by_id = {}
    for item in _individual_items(profile):
        by_id[item["osd"]] = set(item["flags"])
    missing = set(ids).difference(by_id)
    if missing:
        raise ConfigurationError(
            "Individual flags reference missing OSDs: "
            + ", ".join(str(item) for item in sorted(missing))
            + "."
        )
    return {
        svc_id: {
            flag: flag in by_id[svc_id] for flag, enabled in desired.items() if enabled is not None
        }
        for svc_id in ids
    }


def individual_flags_managed(
    name,
    ids,
    flags,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Manage supported flags for a selected set of OSD IDs."""
    ret = reconcile.state_result(name)
    try:
        ids = osd.normalize_osd_ids(ids, "ids")
        desired_flags = osd.normalize_individual_flags(flags)
        desired = {
            svc_id: {
                flag: enabled for flag, enabled in desired_flags.items() if enabled is not None
            }
            for svc_id in ids
        }
        current = _individual_current(ids, desired_flags, profile)
        if current == desired:
            return reconcile.no_change(ret, "Individual OSD flags are already current.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, desired, "Individual OSD flags would change.")
        response = __salt__["ceph_osd.set_individual_flags"](desired_flags, ids, profile=profile)
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        after = _individual_current(ids, desired_flags, profile)
        if after != desired:
            raise ProtocolError("Individual OSD flags did not converge.")
        return reconcile.changed(ret, current, after, "Individual OSD flags were changed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    preserve_id=False,
    force=False,
    confirm=False,
    profile="default",
    task_timeout=7200.0,
    task_interval=10.0,
):
    """Ensure an OSD is removed through cephadm's guarded removal workflow.

    When ``preserve_id`` is true, an OSD-map entry marked ``destroyed`` is the
    converged state because cephadm reserves that numeric ID for replacement.
    """
    ret = reconcile.state_result(name)
    try:
        svc_id = osd.normalize_osd_id(name)
        for label, value in (
            ("preserve_id", preserve_id),
            ("force", force),
            ("confirm", confirm),
        ):
            if not isinstance(value, bool):
                raise ConfigurationError(f"{label} must be a boolean.")
        current = _find_for_removal(svc_id, profile)
        if current is None:
            return reconcile.no_change(ret, f"OSD {svc_id} is already absent.")
        if preserve_id and _is_destroyed(current):
            return reconcile.no_change(
                ret, f"OSD {svc_id} is already removed and its ID is preserved."
            )
        if __opts__.get("test", False):
            if preserve_id:
                return reconcile.planned(
                    ret,
                    current,
                    {"id": svc_id, "state": ["destroyed"]},
                    f"OSD {svc_id} would be removed and its ID preserved.",
                )
            return reconcile.planned(ret, current, None, f"OSD {svc_id} would be removed.")
        if not confirm:
            raise ConfigurationError("Removing an OSD requires confirm=True.")
        if not force:
            check = reconcile.data(
                __salt__["ceph_osd.safe_to_delete"](svc_id, profile=profile),
                "Ceph OSD safe-to-delete check",
                expected=Mapping,
            )
            if check.get("is_safe_to_delete") is not True:
                raise ConfigurationError(f"OSD {svc_id} is not currently safe to remove.")
        mutation_error = None
        try:
            response = __salt__["ceph_osd.remove"](
                svc_id,
                preserve_id=preserve_id,
                force=force,
                confirm=True,
                profile=profile,
            )
        except _ERRORS as exc:
            if _definitive_removal_rejection(exc):
                raise
            mutation_error = exc
        else:
            try:
                reconcile.wait_if_accepted(
                    __salt__,
                    response,
                    profile=profile,
                    timeout=task_timeout,
                    interval=task_interval,
                )
            except _ERRORS as exc:
                # The mutation was already accepted by Dashboard. A task/read
                # failure cannot prove that the removal itself did not apply.
                mutation_error = exc

        try:
            after = _wait_for_absence(svc_id, profile, preserve_id, task_timeout, task_interval)
        except _ERRORS as verification_error:
            if mutation_error is not None:
                raise ProtocolError(
                    f"OSD {svc_id} removal reported "
                    f"{mutation_error.__class__.__name__}: {mutation_error} "
                    f"Post-mutation verification failed: {verification_error}"
                ) from verification_error
            raise

        if mutation_error is not None:
            confirmed = (
                "that its ID is preserved and marked destroyed"
                if after is not None
                else "its absence"
            )
            return reconcile.changed(
                ret,
                current,
                after,
                f"OSD {svc_id} was removed; post-mutation verification confirmed {confirmed} "
                "after the removal operation reported an error.",
            )
        if after is not None:
            return reconcile.changed(
                ret,
                current,
                after,
                f"OSD {svc_id} was removed and its ID was preserved.",
            )
        return reconcile.changed(ret, current, None, f"OSD {svc_id} was removed.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
