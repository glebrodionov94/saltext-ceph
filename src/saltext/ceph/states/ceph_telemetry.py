"""Declaratively manage Ceph telemetry opt-in status."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import telemetry
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_telemetry"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {"ceph_mgr_module.get_config", "ceph_telemetry.set"}
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _current(profile):
    config = reconcile.data(
        __salt__["ceph_mgr_module.get_config"]("telemetry", profile=profile),
        "Ceph telemetry configuration read",
        expected=Mapping,
    )
    enabled = config.get("enabled")
    if not isinstance(enabled, bool):
        raise ProtocolError("Ceph telemetry configuration has no boolean enabled value.")
    return {"enabled": enabled}


def managed(
    name,
    enabled,
    license_name=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure telemetry submission is enabled or disabled.

    Enabling requires ``license_name=sharing-1-0`` as explicit consent. The
    telemetry report endpoint does not expose opt-in status, so the state reads
    the telemetry manager module's persisted ``enabled`` option.
    """
    ret = reconcile.state_result(name)
    try:
        if not isinstance(enabled, bool):
            raise ConfigurationError("enabled must be a boolean.")
        if enabled and license_name != telemetry.LICENSE:
            raise ConfigurationError(
                "Enabling telemetry requires explicit acceptance of license sharing-1-0."
            )
        if not enabled and license_name is not None:
            raise ConfigurationError("license_name must be omitted when disabling telemetry.")
        desired = {"enabled": enabled}
        current = _current(profile)
        if current == desired:
            return reconcile.no_change(ret, "Ceph telemetry is already in the requested state.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, "Ceph telemetry submission would be updated."
            )
        response = __salt__["ceph_telemetry.set"](
            enable=enabled,
            license_name=license_name,
            profile=profile,
        )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _current(profile)
        if after != desired:
            raise ProtocolError("Ceph telemetry submission state did not converge.")
        return reconcile.changed(ret, current, after, "Ceph telemetry submission was updated.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
