"""Declaratively reconcile public RGW account and IAM role resources."""

import math
import re
from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph import rgw_state
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_rgw_iam"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_ACCOUNT_ID = re.compile(r"RGW[0-9]{17}")


def __virtual__():
    required = {
        "ceph_rgw_iam.list_accounts",
        "ceph_rgw_iam.get_account",
        "ceph_rgw_iam.create_account",
        "ceph_rgw_iam.update_account",
        "ceph_rgw_iam.delete_account",
        "ceph_rgw_iam.set_account_quota",
        "ceph_rgw_iam.list_roles",
        "ceph_rgw_iam.create_role",
        "ceph_rgw_iam.update_role",
        "ceph_rgw_iam.delete_role",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _wait(response, profile, timeout, interval):
    return reconcile.wait_if_accepted(
        __salt__, response, profile=profile, timeout=timeout, interval=interval
    )


def _account_id(value):
    value = common.name(value, "account_id")
    if not _ACCOUNT_ID.fullmatch(value):
        raise ConfigurationError("account_id must be RGW followed by 17 decimal digits.")
    return value


def _accounts(daemon_name, profile):
    values = reconcile.data(
        __salt__["ceph_rgw_iam.list_accounts"](
            daemon_name=daemon_name, detailed=True, profile=profile
        ),
        "RGW account list",
        expected=list,
    )
    return rgw_state.list_of_mappings(values, "RGW account list")


def _account(name, account_id, daemon_name, profile):
    values = _accounts(daemon_name, profile)
    matches = [
        item
        for item in values
        if (account_id is not None and item.get("id") == account_id)
        or (account_id is None and item.get("name") == name)
    ]
    if len(matches) > 1:
        raise ProtocolError(f"RGW account list returned duplicate account {name}.")
    if not matches:
        return None
    current = matches[0]
    if current.get("name") != name:
        raise ConfigurationError(
            f"Account id {account_id} belongs to {current.get('name')}, not {name}."
        )
    identifier = current.get("id")
    if not isinstance(identifier, str) or not _ACCOUNT_ID.fullmatch(identifier):
        raise ProtocolError("RGW account read omitted a valid account id.")
    return current


def _account_desired(
    name,
    tenant,
    email,
    max_buckets,
    max_users,
    max_roles,
    max_groups,
    max_access_keys,
):
    desired = {"name": common.name(name, "account_name")}
    for key, value in {"tenant": tenant, "email": email}.items():
        value = common.optional_text(value, key)
        if value is not None:
            desired[key] = value
    for key, value in {
        "max_buckets": max_buckets,
        "max_users": max_users,
        "max_roles": max_roles,
        "max_groups": max_groups,
        "max_access_keys": max_access_keys,
    }.items():
        value = rgw_state.integer_or_none(value, key, non_negative=True)
        if value is not None:
            desired[key] = value
    return desired


def _account_view(current, desired):
    if current is None:
        return None
    if not all(key in current for key in desired):
        missing = sorted(set(desired).difference(current))
        raise ProtocolError(f"RGW account read omitted managed fields: {', '.join(missing)}.")
    return {key: current[key] for key in desired}


def account_present(
    name,
    account_id=None,
    tenant=None,
    email=None,
    max_buckets=None,
    max_users=None,
    max_roles=None,
    max_groups=None,
    max_access_keys=None,
    daemon_name=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph RGW account's declared projection is exact.

    ``account_id`` may pin an existing account. Ceph generates IDs, so a pinned
    missing ID is not recreated under a different identity.
    """
    ret = reconcile.state_result(name)
    try:
        desired = _account_desired(
            name,
            tenant,
            email,
            max_buckets,
            max_users,
            max_roles,
            max_groups,
            max_access_keys,
        )
        name = desired["name"]
        account_id = None if account_id is None else _account_id(account_id)
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        current = _account(name, account_id, daemon_name, profile)
        if current is None and account_id is not None:
            raise ConfigurationError(
                "A missing pinned account_id cannot be recreated because Ceph generates IDs."
            )
        old = _account_view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW account {name} is current.")
        if current is not None:
            for key in ("tenant", "email"):
                if key in desired and desired[key] == "" and old.get(key):
                    raise ConfigurationError(
                        f"The Dashboard account API cannot clear an existing {key}."
                    )
            zero_limits = [
                key
                for key in (
                    "max_buckets",
                    "max_users",
                    "max_roles",
                    "max_groups",
                    "max_access_keys",
                )
                if desired.get(key) == 0 and old.get(key) != 0
            ]
            if zero_limits:
                raise ConfigurationError(
                    "The Dashboard account API cannot set limits to zero: "
                    f"{', '.join(zero_limits)}."
                )
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW account {name} would be reconciled.")
        kwargs = {
            "tenant": tenant,
            "email": email,
            "max_buckets": max_buckets,
            "max_users": max_users,
            "max_roles": max_roles,
            "max_groups": max_groups,
            "max_access_keys": max_access_keys,
            "daemon_name": daemon_name,
            "profile": profile,
        }
        if current is None:
            response = __salt__["ceph_rgw_iam.create_account"](name, **kwargs)
        else:
            response = __salt__["ceph_rgw_iam.update_account"](current["id"], name, **kwargs)
        _wait(response, profile, task_timeout, task_interval)
        after_resource = _account(name, account_id, daemon_name, profile)
        after = _account_view(after_resource, desired)
        if after != desired:
            raise ProtocolError(f"RGW account {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW account {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def account_absent(
    name,
    account_id=None,
    daemon_name=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph RGW account is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "account_name")
        account_id = None if account_id is None else _account_id(account_id)
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        confirm = common.boolean(confirm, "confirm")
        current = _account(name, account_id, daemon_name, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW account {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW account {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW account requires confirm=True.")
        response = __salt__["ceph_rgw_iam.delete_account"](
            current["id"], daemon_name=daemon_name, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        if _account(name, account_id, daemon_name, profile) is not None:
            raise ProtocolError(f"RGW account {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW account {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _account_read(account_id, daemon_name, profile):
    value = reconcile.data(
        __salt__["ceph_rgw_iam.get_account"](account_id, daemon_name=daemon_name, profile=profile),
        "RGW account read",
        expected=Mapping,
    )
    if value.get("id") != account_id:
        raise ProtocolError("RGW account read returned a different account.")
    return dict(value)


def _account_quota(current, quota_type):
    key = "quota" if quota_type == "account" else "bucket_quota"
    value = rgw_state.mapping(current.get(key), "RGW account quota")
    required = ("enabled", "max_size", "max_objects")
    if not all(field in value for field in required):
        raise ProtocolError("RGW account quota omitted a managed field.")
    return {
        "enabled": rgw_state.response_bool(value["enabled"], "enabled"),
        "max_size": common.integer(value["max_size"], "max_size"),
        "max_objects": common.integer(value["max_objects"], "max_objects"),
    }


def account_quota_present(
    name,
    account_id,
    enabled,
    max_size,
    max_objects,
    daemon_name=None,
    confirm_disable=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph account or bucket quota is exact.

    ``max_size`` is deliberately limited to an integer byte count. Unit-bearing
    radosgw-admin input cannot be compared exactly with its numeric read model.
    """
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "quota_type").casefold()
        if name not in ("account", "bucket"):
            raise ConfigurationError("quota_type must be account or bucket.")
        account_id = _account_id(account_id)
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        confirm_disable = common.boolean(confirm_disable, "confirm_disable")
        desired = {
            "enabled": common.boolean(enabled, "enabled"),
            "max_size": common.integer(max_size, "max_size"),
            "max_objects": common.integer(max_objects, "max_objects"),
        }
        old = _account_quota(_account_read(account_id, daemon_name, profile), name)
        if old == desired:
            return reconcile.no_change(ret, f"RGW {name} quota for {account_id} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW {name} quota for {account_id} would be reconciled."
            )
        if old["enabled"] and not desired["enabled"] and not confirm_disable:
            raise ConfigurationError(
                "Disabling an RGW account quota requires confirm_disable=True."
            )
        response = __salt__["ceph_rgw_iam.set_account_quota"](
            account_id,
            name,
            str(desired["max_size"]),
            str(desired["max_objects"]),
            desired["enabled"],
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _account_quota(_account_read(account_id, daemon_name, profile), name)
        if after != desired:
            raise ProtocolError(f"RGW {name} quota for {account_id} did not converge.")
        return reconcile.changed(
            ret, old, after, f"RGW {name} quota for {account_id} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _roles(account_id, profile):
    values = reconcile.data(
        __salt__["ceph_rgw_iam.list_roles"](account_id=account_id, profile=profile),
        "RGW role list",
        expected=list,
    )
    return rgw_state.list_of_mappings(values, "RGW role list")


def _role(name, account_id, profile):
    values = _roles(account_id, profile)
    matches = [item for item in values if item.get("RoleName", item.get("role_name")) == name]
    if len(matches) > 1:
        raise ProtocolError(f"RGW role list returned duplicate role {name}.")
    return matches[0] if matches else None


def _duration_hours(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ConfigurationError("max_session_duration must be between 1 and 12 hours.") from None
    if not math.isfinite(value) or not 1 <= value <= 12:
        raise ConfigurationError("max_session_duration must be between 1 and 12 hours.")
    return value


def _role_desired(name, role_path, role_assume_policy_doc, max_session_duration):
    desired = {
        "role_name": common.name(name, "role_name"),
        "role_path": common.name(role_path, "role_path"),
    }
    if not desired["role_path"].startswith("/") or not desired["role_path"].endswith("/"):
        raise ConfigurationError("role_path must start and end with '/'.")
    if role_assume_policy_doc is not None:
        desired["assume_policy"] = rgw_state.json_value(
            role_assume_policy_doc, "role_assume_policy_doc", mapping_only=True
        )
    if max_session_duration is not None:
        desired["max_session_duration"] = _duration_hours(max_session_duration)
    return desired


def _role_view(current, desired):
    if current is None:
        return None
    role_name = current.get("RoleName", current.get("role_name"))
    role_path = current.get("Path", current.get("role_path"))
    if not isinstance(role_name, str) or not isinstance(role_path, str):
        raise ProtocolError("RGW role read omitted its name or path.")
    result = {"role_name": role_name, "role_path": role_path}
    if "assume_policy" in desired:
        value = current.get("AssumeRolePolicyDocument", current.get("role_assume_policy_doc"))
        result["assume_policy"] = rgw_state.json_value(
            value, "role assume policy", mapping_only=True
        )
    if "max_session_duration" in desired:
        value = current.get("MaxSessionDuration", current.get("max_session_duration"))
        if value is None:
            raise ProtocolError("RGW role read omitted MaxSessionDuration.")
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ProtocolError("RGW role read returned an invalid MaxSessionDuration.") from None
        if not math.isfinite(value):
            raise ProtocolError("RGW role read returned an invalid MaxSessionDuration.")
        if value > 12:
            value /= 3600
        result["max_session_duration"] = value
    return result


def role_present(
    name,
    role_path,
    role_assume_policy_doc=None,
    max_session_duration=None,
    account_id=None,
    replace=False,
    confirm_replace=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a Reef global or current account-scoped RGW role is exact.

    Path and assume-role policy are immutable through Dashboard. Their drift can
    be repaired only with an explicitly confirmed replacement. Attached role
    policies are read-only in the public controller and are not managed here.
    """
    ret = reconcile.state_result(name)
    try:
        desired = _role_desired(name, role_path, role_assume_policy_doc, max_session_duration)
        name = desired["role_name"]
        account_id = None if account_id is None else _account_id(account_id)
        replace = common.boolean(replace, "replace")
        confirm_replace = common.boolean(confirm_replace, "confirm_replace")
        current = _role(name, account_id, profile)
        old = _role_view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW role {name} is current.")
        immutable_drift = current is not None and any(
            old.get(key) != desired.get(key)
            for key in ("role_path", "assume_policy")
            if key in desired
        )
        if immutable_drift and not replace:
            raise ConfigurationError("Role path or assume-policy drift requires replace=True.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW role {name} would be reconciled.")
        if immutable_drift:
            if not confirm_replace:
                raise ConfigurationError("Replacing an RGW role requires confirm_replace=True.")
            _wait(
                __salt__["ceph_rgw_iam.delete_role"](
                    name, account_id=account_id, confirm=True, profile=profile
                ),
                profile,
                task_timeout,
                task_interval,
            )
            current = None
        if current is None:
            policy_text = (
                ""
                if "assume_policy" not in desired
                else rgw_state.json_text(
                    desired["assume_policy"],
                    "role_assume_policy_doc",
                    mapping_only=True,
                )
            )
            _wait(
                __salt__["ceph_rgw_iam.create_role"](
                    name,
                    desired["role_path"],
                    policy_text,
                    account_id=account_id,
                    profile=profile,
                ),
                profile,
                task_timeout,
                task_interval,
            )
        if "max_session_duration" in desired:
            recreated = _role(name, account_id, profile)
            current_view = _role_view(recreated, desired)
            if current_view.get("max_session_duration") != desired["max_session_duration"]:
                _wait(
                    __salt__["ceph_rgw_iam.update_role"](
                        name,
                        desired["max_session_duration"],
                        account_id=account_id,
                        profile=profile,
                    ),
                    profile,
                    task_timeout,
                    task_interval,
                )
        after = _role_view(_role(name, account_id, profile), desired)
        if after != desired:
            raise ProtocolError(f"RGW role {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW role {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def role_absent(
    name,
    account_id=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a Reef global or current account-scoped RGW role is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "role_name")
        account_id = None if account_id is None else _account_id(account_id)
        confirm = common.boolean(confirm, "confirm")
        current = _role(name, account_id, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW role {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW role {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW role requires confirm=True.")
        response = __salt__["ceph_rgw_iam.delete_role"](
            name, account_id=account_id, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        if _role(name, account_id, profile) is not None:
            raise ProtocolError(f"RGW role {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW role {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
