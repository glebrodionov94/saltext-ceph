"""Declaratively manage RADOS pools."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import pool
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_pool"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_pool.list",
        "ceph_pool.get",
        "ceph_pool.create",
        "ceph_pool.update",
        "ceph_pool.delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _exists(name, profile):
    items = reconcile.data(
        __salt__["ceph_pool.list"](stats=False, profile=profile),
        "Ceph pool list",
        expected=list,
    )
    return any(isinstance(item, Mapping) and item.get("pool_name") == name for item in items)


def _current(name, profile):
    if not _exists(name, profile):
        return None
    value = reconcile.data(
        __salt__["ceph_pool.get"](name, stats=False, profile=profile), "Ceph pool read"
    )
    if not isinstance(value, Mapping) or value.get("pool_name") != name:
        raise ProtocolError("Ceph pool read returned an unexpected response shape.")
    return dict(value)


def _configuration_view(current, desired):
    values = current.get("configuration", [])
    if isinstance(values, Mapping):
        mapping = dict(values)
    elif isinstance(values, list):
        mapping = {}
        for entry in values:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
                raise ProtocolError("Ceph pool configuration has an unexpected shape.")
            mapping[entry["name"]] = entry.get("value")
    else:
        raise ProtocolError("Ceph pool configuration has an unexpected shape.")
    return {key: mapping[key] for key in desired if key in mapping}


def _flag_view(current, desired):
    names = current.get("flags_names", "")
    if isinstance(names, str):
        active = set(filter(None, names.split(",")))
    elif isinstance(current.get("flags"), list):
        active = set(current["flags"])
    else:
        active = set()
    return sorted(set(desired).intersection(active))


def _desired(
    name,
    pg_num,
    pool_type,
    erasure_code_profile,
    flags,
    application_metadata,
    rule_name,
    rbd_configuration,
    options,
):
    name = pool.validate_pool_name(name)
    if isinstance(pg_num, bool) or not isinstance(pg_num, int) or pg_num <= 0:
        raise ConfigurationError("pg_num must be a positive integer.")
    if not isinstance(pool_type, str) or pool_type.lower() not in pool.POOL_TYPES:
        raise ConfigurationError("pool_type must be replicated or erasure.")
    pool_type = pool_type.lower()
    erasure_code_profile = pool.normalize_optional_name(
        erasure_code_profile, "erasure_code_profile"
    )
    rule_name = pool.normalize_optional_name(rule_name, "rule_name")
    if pool_type == "replicated" and erasure_code_profile is not None:
        raise ConfigurationError("erasure_code_profile is only valid for erasure pools.")
    flags = pool.normalize_flags(flags)
    if flags and pool_type != "erasure":
        raise ConfigurationError("ec_overwrites is only valid for erasure pools.")
    applications = pool.normalize_applications(application_metadata)
    configuration = pool.normalize_configuration(rbd_configuration)
    normalized_options = pool.normalize_options(options, reserved=("pg_num",))
    result = {"pool_name": name, "pg_num": pg_num, "pool_type": pool_type}
    for key, value in {
        "erasure_code_profile": erasure_code_profile,
        "flags": flags,
        "application_metadata": applications,
        "rule_name": rule_name,
        "rbd_configuration": configuration,
    }.items():
        if value is not None:
            result[key] = value
    result["options"] = normalized_options
    return result


def _view(current, desired):
    if current is None:
        return None
    result = {
        "pool_name": current.get("pool_name"),
        "pg_num": current.get("pg_num"),
        "pool_type": current.get("type", current.get("pool_type")),
        "options": {key: current.get(key) for key in desired["options"]},
    }
    if "erasure_code_profile" in desired:
        result["erasure_code_profile"] = current.get("erasure_code_profile")
    if "rule_name" in desired:
        result["rule_name"] = current.get("crush_rule", current.get("rule_name"))
    if "flags" in desired:
        result["flags"] = _flag_view(current, desired["flags"])
    if "application_metadata" in desired:
        values = current.get("application_metadata", [])
        if not isinstance(values, list):
            raise ProtocolError("Ceph pool application metadata has an unexpected shape.")
        result["application_metadata"] = sorted(values)
    if "rbd_configuration" in desired:
        wanted = {
            key: value for key, value in desired["rbd_configuration"].items() if value is not None
        }
        result["rbd_configuration"] = _configuration_view(current, wanted)
    return result


def _comparable_desired(desired):
    result = dict(desired)
    if "application_metadata" in result:
        result["application_metadata"] = sorted(result["application_metadata"])
    if "flags" in result:
        result["flags"] = sorted(result["flags"])
    if "rbd_configuration" in result:
        result["rbd_configuration"] = {
            key: value for key, value in result["rbd_configuration"].items() if value is not None
        }
    return result


def present(
    name,
    pg_num,
    pool_type,
    erasure_code_profile=None,
    flags=None,
    application_metadata=None,
    rule_name=None,
    rbd_configuration=None,
    rbd_mirroring=None,
    options=None,
    profile="default",
    task_timeout=1800.0,
    task_interval=5.0,
):
    """Ensure a pool exists and reconcile its mutable declared properties."""
    ret = reconcile.state_result(name)
    try:
        desired = _desired(
            name,
            pg_num,
            pool_type,
            erasure_code_profile,
            flags,
            application_metadata,
            rule_name,
            rbd_configuration,
            options,
        )
        if rbd_mirroring is not None and not isinstance(rbd_mirroring, bool):
            raise ConfigurationError("rbd_mirroring must be a boolean or null.")
        comparable = _comparable_desired(desired)
        current = _current(name, profile)
        old = _view(current, desired)
        if current is not None and rbd_mirroring is not None:
            raise ConfigurationError(
                "Manage mirroring for an existing pool with ceph_rbd_mirroring."
            )
        if old == comparable:
            return reconcile.no_change(ret, f"Ceph pool {name} is already current.")
        if current is not None:
            immutable = {
                key
                for key in ("pool_type", "erasure_code_profile", "rule_name")
                if key in comparable and old.get(key) != comparable.get(key)
            }
            if immutable:
                raise ConfigurationError(
                    "Existing pool has incompatible immutable fields: "
                    + ", ".join(sorted(immutable))
                    + "."
                )
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, comparable, f"Ceph pool {name} would be reconciled.")

        if current is None:
            response = __salt__["ceph_pool.create"](
                name,
                pg_num,
                pool_type,
                erasure_code_profile=erasure_code_profile,
                flags=flags,
                application_metadata=application_metadata,
                rule_name=rule_name,
                rbd_configuration=rbd_configuration,
                rbd_mirroring=rbd_mirroring,
                options=options,
                profile=profile,
            )
        else:
            update_options = {
                key: value for key, value in desired["options"].items() if current.get(key) != value
            }
            if current.get("pg_num") != pg_num:
                update_options["pg_num"] = pg_num
            response = __salt__["ceph_pool.update"](
                name,
                flags=flags if old.get("flags") != comparable.get("flags") else None,
                application_metadata=(
                    application_metadata
                    if old.get("application_metadata") != comparable.get("application_metadata")
                    else None
                ),
                rbd_configuration=(
                    rbd_configuration
                    if old.get("rbd_configuration") != comparable.get("rbd_configuration")
                    else None
                ),
                options=update_options or None,
                profile=profile,
            )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _view(_current(name, profile), desired)
        if after != comparable:
            raise ProtocolError(f"Ceph pool {name} did not converge after mutation.")
        return reconcile.changed(ret, old, after, f"Ceph pool {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=1800.0,
    task_interval=5.0,
):
    """Ensure a pool is absent; permanent data deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = pool.validate_pool_name(name)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        current = _current(name, profile)
        if current is None:
            return reconcile.no_change(ret, f"Ceph pool {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"Ceph pool {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting a RADOS pool requires confirm=True.")
        response = __salt__["ceph_pool.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        if _current(name, profile) is not None:
            raise ProtocolError(f"Ceph pool {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"Ceph pool {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
