"""Declaratively manage Ceph manager modules and their options."""

from collections.abc import Mapping
from collections.abc import Sequence

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import mgr_module
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_mgr_module"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_MASK = "********"


def __virtual__():
    required = {
        "ceph_mgr_module.list",
        "ceph_mgr_module.get_config",
        "ceph_mgr_module.set_config",
        "ceph_mgr_module.enable",
        "ceph_mgr_module.disable",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _module(name, profile):
    items = reconcile.data(
        __salt__["ceph_mgr_module.list"](profile=profile),
        "Ceph manager module list",
        expected=list,
    )
    item = next(
        (entry for entry in items if isinstance(entry, Mapping) and entry.get("name") == name),
        None,
    )
    if item is None:
        raise ConfigurationError(f"Ceph manager module {name} is not available.")
    if not isinstance(item.get("enabled"), bool):
        raise ProtocolError("Ceph manager module list returned an unexpected response shape.")
    return dict(item)


def _config(name, desired, profile):
    current = reconcile.data(
        __salt__["ceph_mgr_module.get_config"](name, profile=profile),
        "Ceph manager module configuration",
        expected=Mapping,
    )
    result = {}
    for key in desired:
        if key in current:
            result[key] = current[key]
    return result


def _effective(values):
    return {key: value for key, value in values.items() if value is not None}


def _secret_names(values, config):
    if values is None:
        return set()
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ConfigurationError("secret_options must be a list of option names.")
    names = set(values)
    if len(names) != len(values) or not all(isinstance(name, str) for name in names):
        raise ConfigurationError("secret_options must contain unique string names.")
    if not names.issubset(config):
        raise ConfigurationError("secret_options must refer to managed config keys.")
    return names


def _redact(value, secrets):
    if not isinstance(value, Mapping):
        return value
    return {key: (_MASK if key in secrets else item) for key, item in value.items()}


def managed(
    name,
    enabled=None,
    config=None,
    secret_options=None,
    force_enable=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Manage module enablement and the explicitly declared option keys."""
    ret = reconcile.state_result(name)
    try:
        name = mgr_module.validate_module_name(name)
        if enabled is not None and not isinstance(enabled, bool):
            raise ConfigurationError("enabled must be a boolean or null.")
        if not isinstance(force_enable, bool):
            raise ConfigurationError("force_enable must be a boolean.")
        desired_config = None if config is None else mgr_module.normalize_config(config)
        secrets = _secret_names(secret_options, desired_config or {})
        module_before = _module(name, profile)
        desired = {}
        old = {}
        if enabled is not None:
            desired["enabled"] = enabled
            old["enabled"] = module_before["enabled"]
            if not enabled and module_before.get("always_on"):
                raise ConfigurationError(f"Ceph manager module {name} is always on.")
        if desired_config is not None:
            desired["config"] = _effective(desired_config)
            old["config"] = _config(name, desired_config, profile)
        if old == desired:
            return reconcile.no_change(ret, f"Ceph manager module {name} is already current.")
        safe_old = dict(old)
        safe_new = dict(desired)
        if "config" in safe_old:
            safe_old["config"] = _redact(safe_old["config"], secrets)
            safe_new["config"] = _redact(safe_new["config"], secrets)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                safe_old,
                safe_new,
                f"Ceph manager module {name} would be reconciled.",
            )

        if desired_config is not None and old["config"] != desired["config"]:
            response = __salt__["ceph_mgr_module.set_config"](name, desired_config, profile=profile)
            reconcile.wait_if_accepted(
                __salt__,
                response,
                profile=profile,
                timeout=task_timeout,
                interval=task_interval,
            )
        if enabled is not None and module_before["enabled"] != enabled:
            if enabled:
                response = __salt__["ceph_mgr_module.enable"](
                    name, force=force_enable, profile=profile
                )
            else:
                response = __salt__["ceph_mgr_module.disable"](name, profile=profile)
            reconcile.wait_if_accepted(
                __salt__,
                response,
                profile=profile,
                timeout=task_timeout,
                interval=task_interval,
            )

        module_after = _module(name, profile)
        after = {}
        if enabled is not None:
            after["enabled"] = module_after["enabled"]
        if desired_config is not None:
            after["config"] = _config(name, desired_config, profile)
        if after != desired:
            raise ProtocolError(f"Ceph manager module {name} did not converge.")
        safe_after = dict(after)
        if "config" in safe_after:
            safe_after["config"] = _redact(safe_after["config"], secrets)
        return reconcile.changed(
            ret,
            safe_old,
            safe_after,
            f"Ceph manager module {name} was reconciled.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
