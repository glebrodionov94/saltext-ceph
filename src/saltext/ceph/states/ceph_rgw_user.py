"""Declaratively reconcile readable Ceph RGW user resources."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph import rgw_state
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_rgw_user"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_rgw_user.list_users",
        "ceph_rgw_user.get_user",
        "ceph_rgw_user.create_user",
        "ceph_rgw_user.update_user",
        "ceph_rgw_user.delete_user",
        "ceph_rgw_user.create_subuser",
        "ceph_rgw_user.delete_subuser",
        "ceph_rgw_user.create_capability",
        "ceph_rgw_user.delete_capability",
        "ceph_rgw_user.get_quota",
        "ceph_rgw_user.set_quota",
        "ceph_rgw_user.get_rate_limit",
        "ceph_rgw_user.set_rate_limit",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _wait(response, profile, timeout, interval):
    return reconcile.wait_if_accepted(
        __salt__, response, profile=profile, timeout=timeout, interval=interval
    )


def _canonical_uid(value):
    """Return the Admin Ops identity used by user listings for tenant users."""
    value = common.name(value, "uid")
    if "/" in value and "$" not in value:
        tenant, separator, uid = value.partition("/")
        if separator and tenant and uid and "/" not in uid:
            return f"{tenant}${uid}"
    return value


def _response_uid(value):
    """Extract a full tenant-aware identity from a Dashboard user response."""
    full_user_id = value.get("full_user_id")
    if isinstance(full_user_id, str) and full_user_id:
        return _canonical_uid(full_user_id)
    uid = value.get("uid")
    tenant = value.get("tenant")
    if isinstance(tenant, str) and tenant:
        return _canonical_uid(f"{tenant}${uid}")
    return _canonical_uid(uid)


def _user(uid, daemon_name, profile):
    uid = _canonical_uid(uid)
    values = reconcile.data(
        __salt__["ceph_rgw_user.list_users"](
            daemon_name=daemon_name,
            detailed=False,
            include_secrets=False,
            profile=profile,
        ),
        "RGW user list",
        expected=list,
    )
    if not all(isinstance(item, str) for item in values):
        raise ProtocolError("RGW user list returned an unexpected response shape.")
    matches = [value for value in values if _canonical_uid(value) == uid]
    if len(matches) > 1:
        raise ProtocolError(f"RGW user list returned duplicate user {uid}.")
    if not matches:
        return None
    value = reconcile.data(
        __salt__["ceph_rgw_user.get_user"](
            uid,
            daemon_name=daemon_name,
            stats=False,
            include_secrets=False,
            profile=profile,
        ),
        "RGW user read",
        expected=Mapping,
    )
    if _response_uid(value) != uid:
        raise ProtocolError("RGW user read returned a different user.")
    return dict(value)


def _optional_response_bool(current, key):
    if key not in current:
        raise ProtocolError(f"RGW user read omitted managed field {key}.")
    return rgw_state.response_bool(current[key], key)


def _user_view(current, desired):
    if current is None:
        return None
    result = {}
    for key in desired:
        if key == "uid":
            result[key] = _response_uid(current)
        elif key == "account_root_user":
            result[key] = current.get("type") == "root"
        elif key in ("system", "suspended"):
            result[key] = _optional_response_bool(current, key)
        else:
            if key not in current:
                raise ProtocolError(f"RGW user read omitted managed field {key}.")
            result[key] = current[key]
    return result


def _desired_user(
    uid,
    display_name,
    email,
    max_buckets,
    system,
    suspended,
    account_id,
    account_root_user,
):
    desired = {
        "uid": _canonical_uid(uid),
        "display_name": common.name(display_name, "display_name"),
    }
    optional = {
        "email": common.optional_text(email, "email"),
        "max_buckets": rgw_state.integer_or_none(max_buckets, "max_buckets"),
        "system": rgw_state.bool_or_none(system, "system"),
        "suspended": rgw_state.bool_or_none(suspended, "suspended"),
        "account_id": common.optional_text(account_id, "account_id"),
        "account_root_user": rgw_state.bool_or_none(account_root_user, "account_root_user"),
    }
    desired.update({key: value for key, value in optional.items() if value is not None})
    return desired


def present(
    name,
    display_name,
    email=None,
    max_buckets=None,
    system=None,
    suspended=None,
    generate_key=None,
    access_key_source=None,
    secret_key_source=None,
    daemon_name=None,
    account_id=None,
    account_root_user=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an RGW user exists with its declared readable properties.

    Generated or supplied credentials are creation-only. Their contents are
    never read back, compared, or included in Salt changes.
    """
    ret = reconcile.state_result(name)
    try:
        desired = _desired_user(
            name,
            display_name,
            email,
            max_buckets,
            system,
            suspended,
            account_id,
            account_root_user,
        )
        name = desired["uid"]
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        if generate_key is not None:
            generate_key = common.boolean(generate_key, "generate_key")
        rgw_state.validate_secret_sources(access_key_source, secret_key_source)
        current = _user(name, daemon_name, profile)
        old = _user_view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW user {name} is current.")
        if current is None and "$" in name:
            raise ConfigurationError(
                "The Ceph Dashboard API cannot create tenant users because its user-create "
                "endpoint has no tenant parameter. Existing tenant users remain readable "
                "and manageable."
            )
        if (
            current is not None
            and old.get("account_root_user") is True
            and desired.get("account_root_user") is False
        ):
            raise ConfigurationError("The Dashboard API cannot demote an account root user.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW user {name} would be reconciled.")
        if current is None:
            response = __salt__["ceph_rgw_user.create_user"](
                name,
                display_name,
                email=email,
                max_buckets=max_buckets,
                system=system,
                suspended=suspended,
                generate_key=generate_key,
                access_key_source=access_key_source,
                secret_key_source=secret_key_source,
                daemon_name=daemon_name,
                account_id=account_id,
                account_root_user=account_root_user is True,
                include_secrets=False,
                profile=profile,
            )
        else:
            response = __salt__["ceph_rgw_user.update_user"](
                name,
                display_name=display_name,
                email=email,
                max_buckets=max_buckets,
                system=system,
                suspended=suspended,
                daemon_name=daemon_name,
                account_id=account_id,
                account_root_user=account_root_user is True,
                include_secrets=False,
                profile=profile,
            )
        _wait(response, profile, task_timeout, task_interval)
        after = _user_view(_user(name, daemon_name, profile), desired)
        if after != desired:
            raise ProtocolError(f"RGW user {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW user {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    daemon_name=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an RGW user is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "uid")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        common.boolean(confirm, "confirm")
        current = _user(name, daemon_name, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW user {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW user {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW user requires confirm=True.")
        response = __salt__["ceph_rgw_user.delete_user"](
            name, daemon_name=daemon_name, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        if _user(name, daemon_name, profile) is not None:
            raise ProtocolError(f"RGW user {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW user {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _subuser(current, subuser):
    values = current.get("subusers", [])
    values = rgw_state.list_of_mappings(values, "RGW subuser list")
    matches = []
    for item in values:
        identifier = item.get("id")
        if identifier == subuser or (
            isinstance(identifier, str) and identifier.endswith(f":{subuser}")
        ):
            matches.append(item)
    if len(matches) > 1:
        raise ProtocolError(f"RGW user contains duplicate subuser {subuser}.")
    if not matches:
        return None
    permission = matches[0].get("permissions", matches[0].get("perm"))
    aliases = {"read-write": "readwrite", "full-control": "full"}
    if not isinstance(permission, str):
        raise ProtocolError("RGW subuser read omitted its permissions.")
    return {"subuser": subuser, "access": aliases.get(permission.casefold(), permission.casefold())}


def subuser_present(
    name,
    uid,
    access,
    key_type="s3",
    generate_secret=True,
    access_key_source=None,
    secret_key_source=None,
    daemon_name=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a subuser and its readable permission exist.

    Key type and credentials are creation-only. Existing subusers are updated
    with key generation disabled, so ordinary drift repair cannot rotate keys.
    """
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "subuser")
        uid = common.name(uid, "uid")
        access = common.name(access, "access").casefold()
        if access not in ("read", "write", "readwrite", "full"):
            raise ConfigurationError("access must be read, write, readwrite, or full.")
        key_type = common.name(key_type, "key_type").casefold()
        if key_type not in ("s3", "swift"):
            raise ConfigurationError("key_type must be s3 or swift.")
        generate_secret = common.boolean(generate_secret, "generate_secret")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        rgw_state.validate_secret_sources(access_key_source, secret_key_source)
        user = _user(uid, daemon_name, profile)
        if user is None:
            raise ConfigurationError(f"RGW user {uid} must exist before its subusers.")
        desired = {"subuser": name, "access": access}
        old = _subuser(user, name)
        if old == desired:
            return reconcile.no_change(ret, f"RGW subuser {uid}:{name} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW subuser {uid}:{name} would be reconciled."
            )
        response = __salt__["ceph_rgw_user.create_subuser"](
            uid,
            name if old is None or ":" in name else f"{uid}:{name}",
            access,
            key_type=key_type,
            generate_secret=generate_secret if old is None else False,
            access_key_source=access_key_source if old is None else None,
            secret_key_source=secret_key_source if old is None else None,
            daemon_name=daemon_name,
            include_secrets=False,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after_user = _user(uid, daemon_name, profile)
        if after_user is None:
            raise ProtocolError(f"RGW user {uid} disappeared during reconciliation.")
        after = _subuser(after_user, name)
        if after != desired:
            raise ProtocolError(f"RGW subuser {uid}:{name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW subuser {uid}:{name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def subuser_absent(
    name,
    uid,
    purge_keys=True,
    daemon_name=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a subuser is absent; deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "subuser")
        uid = common.name(uid, "uid")
        purge_keys = common.boolean(purge_keys, "purge_keys")
        confirm = common.boolean(confirm, "confirm")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        user = _user(uid, daemon_name, profile)
        old = None if user is None else _subuser(user, name)
        if old is None:
            return reconcile.no_change(ret, f"RGW subuser {uid}:{name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, None, f"RGW subuser {uid}:{name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW subuser requires confirm=True.")
        response = __salt__["ceph_rgw_user.delete_subuser"](
            uid,
            name if ":" in name else f"{uid}:{name}",
            purge_keys=purge_keys,
            daemon_name=daemon_name,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        user = _user(uid, daemon_name, profile)
        if user is not None and _subuser(user, name) is not None:
            raise ProtocolError(f"RGW subuser {uid}:{name} still exists after deletion.")
        return reconcile.changed(ret, old, None, f"RGW subuser {uid}:{name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _capability(current, capability_type, permission):
    desired = {
        "capability_type": capability_type,
        "permission": ",".join(_permissions(permission)),
    }
    return desired if _capability_by_type(current, capability_type) == desired else None


def _capability_by_type(current, capability_type):
    """Return the one readable capability identified by its type."""
    values = rgw_state.list_of_mappings(current.get("caps", []), "RGW capability list")
    matches = [item for item in values if item.get("type") == capability_type]
    if len(matches) > 1:
        raise ProtocolError(f"RGW user contains duplicate capability type {capability_type}.")
    if not matches:
        return None
    permission = matches[0].get("perm")
    if not isinstance(permission, str):
        raise ProtocolError("RGW capability read omitted a permission.")
    parts = [part.strip() for part in permission.split(",")]
    if not all(parts) or len(parts) != len(set(parts)):
        raise ProtocolError("RGW capability read returned invalid permissions.")
    return {"capability_type": capability_type, "permission": ",".join(sorted(parts))}


def _permissions(value):
    """Return a canonical non-empty capability permission list."""
    value = common.name(value, "permission")
    parts = [part.strip() for part in value.split(",")]
    if not all(parts) or len(parts) != len(set(parts)):
        raise ConfigurationError(
            "permission must be a comma-separated list without empty or duplicate entries."
        )
    return sorted(parts)


def capability_present(
    name,
    uid,
    permission,
    daemon_name=None,
    replace=False,
    confirm_replace=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure one exact Admin Ops capability is attached to an RGW user.

    RGW capability permissions are additive. Replacing a different permission
    set therefore requires both ``replace`` and ``confirm_replace``.
    """
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "capability_type")
        uid = common.name(uid, "uid")
        permissions = _permissions(permission)
        permission = ",".join(permissions)
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        replace = common.boolean(replace, "replace")
        confirm_replace = common.boolean(confirm_replace, "confirm_replace")
        desired = {
            "capability_type": name,
            "permission": permission,
        }
        user = _user(uid, daemon_name, profile)
        if user is None:
            raise ConfigurationError(f"RGW user {uid} must exist before its capabilities.")
        old = _capability_by_type(user, name)
        if old == desired:
            return reconcile.no_change(ret, f"RGW capability {uid}:{name} is present.")
        if old is not None and not replace:
            raise ConfigurationError(
                "Capability permission drift requires replace=True because RGW additions are "
                "not an exact replacement."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW capability {uid}:{name} would be created."
            )
        if old is not None:
            if not confirm_replace:
                raise ConfigurationError(
                    "Replacing an RGW capability requires confirm_replace=True."
                )
            _wait(
                __salt__["ceph_rgw_user.delete_capability"](
                    uid,
                    name,
                    old["permission"],
                    daemon_name=daemon_name,
                    confirm=True,
                    profile=profile,
                ),
                profile,
                task_timeout,
                task_interval,
            )
        response = __salt__["ceph_rgw_user.create_capability"](
            uid, name, permission, daemon_name=daemon_name, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        user = _user(uid, daemon_name, profile)
        after = None if user is None else _capability_by_type(user, name)
        if after != desired:
            raise ProtocolError(f"RGW capability {uid}:{name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW capability {uid}:{name} was created.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def capability_absent(
    name,
    uid,
    permission,
    daemon_name=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure one exact Admin Ops capability is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "capability_type")
        uid = common.name(uid, "uid")
        permission = ",".join(_permissions(permission))
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        confirm = common.boolean(confirm, "confirm")
        user = _user(uid, daemon_name, profile)
        old = None if user is None else _capability(user, name, permission)
        if old is None:
            return reconcile.no_change(ret, f"RGW capability {uid}:{name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, None, f"RGW capability {uid}:{name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting an RGW capability requires confirm=True.")
        response = __salt__["ceph_rgw_user.delete_capability"](
            uid,
            name,
            permission,
            daemon_name=daemon_name,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        user = _user(uid, daemon_name, profile)
        if user is not None and _capability(user, name, permission) is not None:
            raise ProtocolError(f"RGW capability {uid}:{name} still exists after deletion.")
        return reconcile.changed(ret, old, None, f"RGW capability {uid}:{name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _quota(uid, quota_type, daemon_name, profile):
    value = reconcile.data(
        __salt__["ceph_rgw_user.get_quota"](uid, daemon_name=daemon_name, profile=profile),
        "RGW user quota",
        expected=Mapping,
    )
    key = f"{quota_type}_quota"
    current = value.get(key)
    current = rgw_state.mapping(current, "RGW user quota")
    required = ("enabled", "max_size_kb", "max_objects")
    if not all(field in current for field in required):
        raise ProtocolError("RGW user quota omitted a managed field.")
    return {
        "enabled": rgw_state.response_bool(current["enabled"], "enabled"),
        "max_size_kb": common.integer(current["max_size_kb"], "max_size_kb"),
        "max_objects": common.integer(current["max_objects"], "max_objects"),
    }


def quota_present(
    name,
    uid,
    enabled,
    max_size_kb,
    max_objects,
    daemon_name=None,
    confirm_disable=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure the ``user`` or ``bucket`` quota projection is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "quota_type").casefold()
        if name not in ("user", "bucket"):
            raise ConfigurationError("quota_type must be user or bucket.")
        uid = common.name(uid, "uid")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        confirm_disable = common.boolean(confirm_disable, "confirm_disable")
        desired = {
            "enabled": common.boolean(enabled, "enabled"),
            "max_size_kb": common.integer(max_size_kb, "max_size_kb"),
            "max_objects": common.integer(max_objects, "max_objects"),
        }
        old = _quota(uid, name, daemon_name, profile)
        if old == desired:
            return reconcile.no_change(ret, f"RGW {name} quota for {uid} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW {name} quota for {uid} would be reconciled."
            )
        if old["enabled"] and not desired["enabled"] and not confirm_disable:
            raise ConfigurationError("Disabling an RGW quota requires confirm_disable=True.")
        response = __salt__["ceph_rgw_user.set_quota"](
            uid,
            name,
            desired["enabled"],
            desired["max_size_kb"],
            desired["max_objects"],
            daemon_name=daemon_name,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _quota(uid, name, daemon_name, profile)
        if after != desired:
            raise ProtocolError(f"RGW {name} quota for {uid} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW {name} quota for {uid} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def rate_limit_present(
    name,
    enabled=False,
    max_read_ops=0,
    max_write_ops=0,
    max_read_bytes=0,
    max_write_bytes=0,
    confirm_disable=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph per-user rate limit is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "uid")
        confirm_disable = common.boolean(confirm_disable, "confirm_disable")
        desired = rgw_state.rate_desired(
            enabled, max_read_ops, max_write_ops, max_read_bytes, max_write_bytes
        )
        old = rgw_state.rate_view(
            reconcile.data(
                __salt__["ceph_rgw_user.get_rate_limit"](name, profile=profile),
                "RGW user rate limit",
                expected=Mapping,
            ),
            "user",
        )
        if old == desired:
            return reconcile.no_change(ret, f"RGW user rate limit for {name} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW user rate limit for {name} would be reconciled."
            )
        if old["enabled"] and not desired["enabled"] and not confirm_disable:
            raise ConfigurationError("Disabling an RGW rate limit requires confirm_disable=True.")
        response = __salt__["ceph_rgw_user.set_rate_limit"](name, profile=profile, **desired)
        _wait(response, profile, task_timeout, task_interval)
        after = rgw_state.rate_view(
            reconcile.data(
                __salt__["ceph_rgw_user.get_rate_limit"](name, profile=profile),
                "RGW user rate limit",
                expected=Mapping,
            ),
            "user",
        )
        if after != desired:
            raise ProtocolError(f"RGW user rate limit for {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW user rate limit for {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def managed_policies_present(
    name,
    policies,
    daemon_name=None,
    confirm_remove=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure current-Ceph account-user managed policy attachments are exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "uid")
        desired = sorted(common.string_list(policies, "policies"))
        confirm_remove = common.boolean(confirm_remove, "confirm_remove")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        user = _user(name, daemon_name, profile)
        if user is None:
            raise ConfigurationError(f"RGW user {name} must exist before its policies.")
        if "managed_user_policies" not in user:
            raise ConfigurationError(
                "Managed policy reconciliation requires a current-Ceph account user."
            )
        old = rgw_state.policy_arns(user["managed_user_policies"])
        if old == desired:
            return reconcile.no_change(ret, f"RGW managed policies for {name} are current.")
        attach = sorted(set(desired) - set(old))
        detach = sorted(set(old) - set(desired))
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW managed policies for {name} would be reconciled."
            )
        if detach and not confirm_remove:
            raise ConfigurationError("Detaching RGW managed policies requires confirm_remove=True.")
        response = __salt__["ceph_rgw_user.update_user"](
            name,
            daemon_name=daemon_name,
            account_policies={"attach": attach, "detach": detach},
            confirm_policy_detach=bool(detach),
            include_secrets=False,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        user = _user(name, daemon_name, profile)
        if user is None or "managed_user_policies" not in user:
            raise ProtocolError(f"RGW managed policies for {name} could not be verified.")
        after = rgw_state.policy_arns(user["managed_user_policies"])
        if after != desired:
            raise ProtocolError(f"RGW managed policies for {name} did not converge.")
        return reconcile.changed(
            ret, old, after, f"RGW managed policies for {name} were reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
