"""Declaratively reconcile Ceph iSCSI targets."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import iscsi
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_iscsi"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_SECRET_FIELDS = frozenset(("password", "mutual_password"))


def __virtual__():
    required = {
        "ceph_iscsi.list_targets",
        "ceph_iscsi.get_target",
        "ceph_iscsi.create_target",
        "ceph_iscsi.update_target",
        "ceph_iscsi.delete_target",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _redact(value):
    if isinstance(value, Mapping):
        return {
            key: "***********" if key in _SECRET_FIELDS else _redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact(child) for child in value]
    return value


def _exists(target_iqn, profile):
    values = reconcile.data(
        __salt__["ceph_iscsi.list_targets"](include_secrets=True, profile=profile),
        "Ceph iSCSI target list",
        expected=list,
    )
    if not all(isinstance(item, Mapping) for item in values):
        raise ProtocolError("Ceph iSCSI target list returned an unexpected response shape.")
    return any(item.get("target_iqn") == target_iqn for item in values)


def _current(target_iqn, profile):
    if not _exists(target_iqn, profile):
        return None
    value = reconcile.data(
        __salt__["ceph_iscsi.get_target"](target_iqn, include_secrets=True, profile=profile),
        "Ceph iSCSI target",
        expected=Mapping,
    )
    if value.get("target_iqn") != target_iqn:
        raise ProtocolError("Ceph iSCSI target returned an unexpected identity.")
    return dict(value)


def present(
    name,
    portals,
    target_controls=None,
    acl_enabled=False,
    auth=None,
    disks=None,
    clients=None,
    groups=None,
    confirm_update=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure one complete iSCSI target exists; replacement requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        desired = iscsi.normalize_target(
            name,
            portals,
            target_controls,
            acl_enabled,
            auth,
            disks,
            clients,
            groups,
        )
        target_iqn = desired["target_iqn"]
        current = _current(target_iqn, profile)
        old = None if current is None else reconcile.project(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"Ceph iSCSI target {target_iqn} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                _redact(old),
                _redact(desired),
                f"Ceph iSCSI target {target_iqn} would be reconciled.",
            )
        kwargs = {key: value for key, value in desired.items() if key != "target_iqn"}
        if current is None:
            response = __salt__["ceph_iscsi.create_target"](target_iqn, profile=profile, **kwargs)
        else:
            if confirm_update is not True:
                raise ConfigurationError(
                    "Replacing an existing iSCSI target requires confirm_update=True."
                )
            response = __salt__["ceph_iscsi.update_target"](
                target_iqn,
                new_target_iqn=target_iqn,
                confirm=True,
                profile=profile,
                **kwargs,
            )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after_current = _current(target_iqn, profile)
        after = None if after_current is None else reconcile.project(after_current, desired)
        if after != desired:
            raise ProtocolError(f"Ceph iSCSI target {target_iqn} did not converge.")
        return reconcile.changed(
            ret,
            _redact(old),
            _redact(after),
            f"Ceph iSCSI target {target_iqn} was reconciled.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an iSCSI target is absent; removal requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        target_iqn = iscsi.validate_iqn(name)
        current = _current(target_iqn, profile)
        if current is None:
            return reconcile.no_change(ret, f"Ceph iSCSI target {target_iqn} is absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                _redact(current),
                None,
                f"Ceph iSCSI target {target_iqn} would be deleted.",
            )
        if confirm is not True:
            raise ConfigurationError("Deleting an iSCSI target requires confirm=True.")
        response = __salt__["ceph_iscsi.delete_target"](target_iqn, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        if _current(target_iqn, profile) is not None:
            raise ProtocolError(f"Ceph iSCSI target {target_iqn} still exists.")
        return reconcile.changed(
            ret,
            _redact(current),
            None,
            f"Ceph iSCSI target {target_iqn} was deleted.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
