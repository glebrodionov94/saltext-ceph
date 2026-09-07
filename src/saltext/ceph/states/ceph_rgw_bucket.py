"""Declaratively reconcile readable Ceph RGW bucket resources."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph import rgw_state
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_rgw_bucket"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_LOCK_MODES = frozenset(("GOVERNANCE", "COMPLIANCE"))
_ENCRYPTION_ALGORITHMS = {"kms": "aws:kms", "s3": "AES256"}


def __virtual__():
    required = {
        "ceph_rgw_bucket.list_buckets",
        "ceph_rgw_bucket.get_bucket",
        "ceph_rgw_bucket.create_bucket",
        "ceph_rgw_bucket.update_bucket",
        "ceph_rgw_bucket.delete_bucket",
        "ceph_rgw_bucket.get_encryption",
        "ceph_rgw_bucket.delete_encryption",
        "ceph_rgw_bucket.get_lifecycle",
        "ceph_rgw_bucket.set_lifecycle",
        "ceph_rgw_bucket.get_notifications",
        "ceph_rgw_bucket.set_notifications",
        "ceph_rgw_bucket.delete_notification",
        "ceph_rgw_bucket.get_rate_limit",
        "ceph_rgw_bucket.set_rate_limit",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _wait(response, profile, timeout, interval):
    return reconcile.wait_if_accepted(
        __salt__, response, profile=profile, timeout=timeout, interval=interval
    )


def _bucket(name, daemon_name, profile):
    values = reconcile.data(
        __salt__["ceph_rgw_bucket.list_buckets"](
            stats=False, daemon_name=daemon_name, profile=profile
        ),
        "RGW bucket list",
        expected=list,
    )
    if not all(isinstance(item, str) for item in values):
        raise ProtocolError("RGW bucket list returned an unexpected response shape.")
    if values.count(name) > 1:
        raise ProtocolError(f"RGW bucket list returned duplicate bucket {name}.")
    if name not in values:
        return None
    value = reconcile.data(
        __salt__["ceph_rgw_bucket.get_bucket"](name, daemon_name=daemon_name, profile=profile),
        "RGW bucket read",
        expected=Mapping,
    )
    identity = value.get("bid")
    if identity is None:
        tenant = value.get("tenant")
        bucket_name = value.get("bucket")
        identity = f"{tenant}/{bucket_name}" if tenant else bucket_name
    if identity != name:
        raise ProtocolError("RGW bucket read returned a different bucket.")
    return dict(value)


def _bucket_id(current):
    for key in ("id", "bucket_id"):
        value = current.get(key)
        if isinstance(value, str) and value:
            return value
    raise ProtocolError("RGW bucket read omitted the physical bucket id.")


def _lock_view(current, desired):
    result = {"bid": current.get("bid", current.get("bucket")), "owner": current.get("owner")}
    if "lock_enabled" in desired:
        if "lock_enabled" not in current:
            raise ProtocolError("RGW bucket read omitted lock_enabled.")
        result["lock_enabled"] = rgw_state.response_bool(current["lock_enabled"], "lock_enabled")
    for key in (
        "lock_mode",
        "lock_retention_period_days",
        "lock_retention_period_years",
    ):
        if key in desired:
            if key not in current:
                raise ProtocolError(f"RGW bucket read omitted {key}.")
            result[key] = current[key]
    result["bid"] = desired["bid"] if result["bid"] == current.get("bucket") else result["bid"]
    return result


def present(
    name,
    uid,
    zonegroup=None,
    placement_target=None,
    lock_enabled=None,
    lock_mode=None,
    lock_retention_period_days=None,
    lock_retention_period_years=None,
    daemon_name=None,
    confirm_owner_change=False,
    confirm_lock_change=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a bucket, owner, and readable object-lock settings exist.

    ``zonegroup`` and ``placement_target`` are creation-only because the
    Dashboard read model does not expose a portable exact projection for them.
    """
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        uid = common.name(uid, "uid")
        zonegroup = common.optional_text(zonegroup, "zonegroup")
        placement_target = common.optional_text(placement_target, "placement_target")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        confirm_owner_change = common.boolean(confirm_owner_change, "confirm_owner_change")
        confirm_lock_change = common.boolean(confirm_lock_change, "confirm_lock_change")
        lock_enabled = rgw_state.bool_or_none(lock_enabled, "lock_enabled")
        lock_mode = common.optional_text(lock_mode, "lock_mode")
        if lock_mode is not None and lock_mode not in _LOCK_MODES:
            raise ConfigurationError("lock_mode must be GOVERNANCE or COMPLIANCE.")
        days = rgw_state.integer_or_none(
            lock_retention_period_days, "lock_retention_period_days", non_negative=True
        )
        years = rgw_state.integer_or_none(
            lock_retention_period_years, "lock_retention_period_years", non_negative=True
        )
        if days is not None and years is not None:
            raise ConfigurationError("choose only one object-lock retention period unit.")
        if lock_enabled is True and lock_mode is None:
            raise ConfigurationError("lock_mode is required when lock_enabled=True.")
        desired = {"bid": name, "owner": uid}
        for key, value in {
            "lock_enabled": lock_enabled,
            "lock_mode": lock_mode,
            "lock_retention_period_days": days,
            "lock_retention_period_years": years,
        }.items():
            if value is not None:
                desired[key] = value
        current = _bucket(name, daemon_name, profile)
        old = None if current is None else _lock_view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW bucket {name} is current.")
        if (
            current is not None
            and "lock_enabled" in desired
            and old["lock_enabled"] != desired["lock_enabled"]
        ):
            raise ConfigurationError("Object-lock enablement is immutable after bucket creation.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW bucket {name} would be reconciled.")
        if current is not None and old["owner"] != uid and not confirm_owner_change:
            raise ConfigurationError(
                "Changing bucket ownership requires confirm_owner_change=True."
            )
        lock_changes = current is not None and any(
            old.get(key) != desired.get(key)
            for key in (
                "lock_mode",
                "lock_retention_period_days",
                "lock_retention_period_years",
            )
            if key in desired
        )
        if lock_changes and not confirm_lock_change:
            raise ConfigurationError(
                "Changing object-lock retention requires confirm_lock_change=True."
            )
        if current is None:
            response = __salt__["ceph_rgw_bucket.create_bucket"](
                name,
                uid,
                zonegroup=zonegroup,
                placement_target=placement_target,
                lock_enabled=lock_enabled is True,
                lock_mode=lock_mode,
                lock_retention_period_days=days,
                lock_retention_period_years=years,
                daemon_name=daemon_name,
                profile=profile,
            )
        else:
            response = __salt__["ceph_rgw_bucket.update_bucket"](
                name,
                _bucket_id(current),
                uid=uid if old["owner"] != uid else None,
                lock_mode=lock_mode if old.get("lock_mode") != lock_mode else None,
                lock_retention_period_days=(
                    days if old.get("lock_retention_period_days") != days else None
                ),
                lock_retention_period_years=(
                    years if old.get("lock_retention_period_years") != years else None
                ),
                daemon_name=daemon_name,
                profile=profile,
            )
        _wait(response, profile, task_timeout, task_interval)
        after_resource = _bucket(name, daemon_name, profile)
        after = None if after_resource is None else _lock_view(after_resource, desired)
        if after != desired:
            raise ProtocolError(f"RGW bucket {name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW bucket {name} was reconciled.")
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
    """Ensure an empty bucket is absent; deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        confirm = common.boolean(confirm, "confirm")
        current = _bucket(name, daemon_name, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW bucket {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW bucket {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW bucket requires confirm=True.")
        response = __salt__["ceph_rgw_bucket.delete_bucket"](
            name, daemon_name=daemon_name, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        if _bucket(name, daemon_name, profile) is not None:
            raise ProtocolError(f"RGW bucket {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW bucket {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def versioning_present(
    name,
    versioning_state,
    daemon_name=None,
    confirm_suspend=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure bucket versioning is Enabled or Suspended."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        versioning_state = common.name(versioning_state, "versioning_state")
        if versioning_state not in ("Enabled", "Suspended"):
            raise ConfigurationError("versioning_state must be Enabled or Suspended.")
        confirm_suspend = common.boolean(confirm_suspend, "confirm_suspend")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        current = _bucket(name, daemon_name, profile)
        if current is None:
            raise ConfigurationError(f"RGW bucket {name} must exist before versioning is managed.")
        old = rgw_state.versioning_status(current.get("versioning"))
        if old == versioning_state:
            return reconcile.no_change(ret, f"RGW bucket {name} versioning is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                old,
                versioning_state,
                f"RGW bucket {name} versioning would be reconciled.",
            )
        if old == "Enabled" and versioning_state == "Suspended" and not confirm_suspend:
            raise ConfigurationError("Suspending bucket versioning requires confirm_suspend=True.")
        response = __salt__["ceph_rgw_bucket.update_bucket"](
            name,
            _bucket_id(current),
            versioning_state=versioning_state,
            daemon_name=daemon_name,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after_resource = _bucket(name, daemon_name, profile)
        after = (
            None
            if after_resource is None
            else rgw_state.versioning_status(after_resource.get("versioning"))
        )
        if after != versioning_state:
            raise ProtocolError(f"RGW bucket {name} versioning did not converge.")
        return reconcile.changed(ret, old, after, f"RGW bucket {name} versioning was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _encryption(name, daemon_name, owner, profile):
    value = reconcile.data(
        __salt__["ceph_rgw_bucket.get_encryption"](
            name, daemon_name=daemon_name, owner=owner, profile=profile
        ),
        "RGW bucket encryption",
        expected=Mapping,
    )
    status = value.get("Status")
    if status not in ("Enabled", "Disabled"):
        raise ProtocolError("RGW bucket encryption returned an unknown status.")
    result = {"status": status}
    if status == "Enabled":
        algorithm = value.get("SSEAlgorithm")
        if not isinstance(algorithm, str):
            rules = value.get("Rules")
            if isinstance(rules, list) and rules and isinstance(rules[0], Mapping):
                default = rules[0].get("ApplyServerSideEncryptionByDefault", {})
                if isinstance(default, Mapping):
                    algorithm = default.get("SSEAlgorithm")
                    value = {**value, **default}
        if not isinstance(algorithm, str):
            raise ProtocolError("RGW bucket encryption omitted its algorithm.")
        result["algorithm"] = algorithm
        key_id = value.get("KMSMasterKeyID")
        if key_id is not None:
            result["key_id"] = key_id
    return result


def encryption_present(
    name,
    encryption_type,
    key_id=None,
    daemon_name=None,
    owner=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure bucket server-side encryption has an exact readable projection."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        encryption_type = common.name(encryption_type, "encryption_type").casefold()
        if encryption_type not in _ENCRYPTION_ALGORITHMS:
            raise ConfigurationError("encryption_type must be kms or s3.")
        key_id = common.optional_text(key_id, "key_id")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        owner = common.optional_text(owner, "owner")
        desired = {
            "status": "Enabled",
            "algorithm": _ENCRYPTION_ALGORITHMS[encryption_type],
        }
        if key_id is not None:
            desired["key_id"] = key_id
        current_bucket = _bucket(name, daemon_name, profile)
        if current_bucket is None:
            raise ConfigurationError(f"RGW bucket {name} must exist before encryption is managed.")
        old_full = _encryption(name, daemon_name, owner, profile)
        old = reconcile.project(old_full, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW bucket {name} encryption is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW bucket {name} encryption would be reconciled."
            )
        response = __salt__["ceph_rgw_bucket.update_bucket"](
            name,
            _bucket_id(current_bucket),
            encryption_state=True,
            encryption_type=encryption_type,
            key_id=key_id,
            daemon_name=daemon_name,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = reconcile.project(_encryption(name, daemon_name, owner, profile), desired)
        if after != desired:
            raise ProtocolError(f"RGW bucket {name} encryption did not converge.")
        return reconcile.changed(ret, old, after, f"RGW bucket {name} encryption was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def encryption_absent(
    name,
    daemon_name=None,
    owner=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure bucket server-side encryption is disabled."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        owner = common.optional_text(owner, "owner")
        confirm = common.boolean(confirm, "confirm")
        old = _encryption(name, daemon_name, owner, profile)
        if old["status"] == "Disabled":
            return reconcile.no_change(ret, f"RGW bucket {name} encryption is already disabled.")
        desired = {"status": "Disabled"}
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW bucket {name} encryption would be disabled."
            )
        if not confirm:
            raise ConfigurationError("Disabling bucket encryption requires confirm=True.")
        response = __salt__["ceph_rgw_bucket.delete_encryption"](
            name,
            daemon_name=daemon_name,
            owner=owner,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _encryption(name, daemon_name, owner, profile)
        if after["status"] != "Disabled":
            raise ProtocolError(f"RGW bucket {name} encryption is still enabled.")
        return reconcile.changed(ret, old, desired, f"RGW bucket {name} encryption was disabled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _json_setting(function, name, daemon_name, owner, profile, *, tenant=None, label):
    kwargs = {"daemon_name": daemon_name, "owner": owner, "profile": profile}
    if tenant is not None:
        kwargs["tenant"] = tenant
    value = reconcile.data(__salt__[function](name, **kwargs), label)
    if value in (None, ""):
        return {}
    return rgw_state.json_value(value, label)


def lifecycle_present(
    name,
    lifecycle,
    daemon_name=None,
    owner=None,
    tenant=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph bucket lifecycle document is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        desired = rgw_state.json_value(lifecycle, "lifecycle", mapping_only=True, non_empty=True)
        payload = rgw_state.json_text(desired, "lifecycle", mapping_only=True, non_empty=True)
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        owner = common.optional_text(owner, "owner")
        tenant = common.optional_text(tenant, "tenant")
        old = _json_setting(
            "ceph_rgw_bucket.get_lifecycle",
            name,
            daemon_name,
            owner,
            profile,
            tenant=tenant,
            label="RGW bucket lifecycle",
        )
        if rgw_state.canonical(old) == rgw_state.canonical(desired):
            return reconcile.no_change(ret, f"RGW bucket {name} lifecycle is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW bucket {name} lifecycle would be reconciled."
            )
        response = __salt__["ceph_rgw_bucket.set_lifecycle"](
            name,
            payload,
            daemon_name=daemon_name,
            owner=owner,
            tenant=tenant,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _json_setting(
            "ceph_rgw_bucket.get_lifecycle",
            name,
            daemon_name,
            owner,
            profile,
            tenant=tenant,
            label="RGW bucket lifecycle",
        )
        if rgw_state.canonical(after) != rgw_state.canonical(desired):
            raise ProtocolError(f"RGW bucket {name} lifecycle did not converge.")
        return reconcile.changed(ret, old, after, f"RGW bucket {name} lifecycle was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def lifecycle_absent(
    name,
    daemon_name=None,
    owner=None,
    tenant=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph bucket lifecycle document is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        owner = common.optional_text(owner, "owner")
        tenant = common.optional_text(tenant, "tenant")
        confirm = common.boolean(confirm, "confirm")
        old = _json_setting(
            "ceph_rgw_bucket.get_lifecycle",
            name,
            daemon_name,
            owner,
            profile,
            tenant=tenant,
            label="RGW bucket lifecycle",
        )
        if old in ({}, None):
            return reconcile.no_change(ret, f"RGW bucket {name} lifecycle is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, {}, f"RGW bucket {name} lifecycle would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting a bucket lifecycle requires confirm=True.")
        response = __salt__["ceph_rgw_bucket.set_lifecycle"](
            name,
            "{}",
            daemon_name=daemon_name,
            owner=owner,
            tenant=tenant,
            confirm_delete=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _json_setting(
            "ceph_rgw_bucket.get_lifecycle",
            name,
            daemon_name,
            owner,
            profile,
            tenant=tenant,
            label="RGW bucket lifecycle",
        )
        if after not in ({}, None):
            raise ProtocolError(f"RGW bucket {name} lifecycle still exists.")
        return reconcile.changed(ret, old, {}, f"RGW bucket {name} lifecycle was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def notifications_present(
    name,
    notification,
    daemon_name=None,
    owner=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure the complete current-Ceph bucket notification document is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        desired = rgw_state.json_value(
            notification, "notification", mapping_only=True, non_empty=True
        )
        payload = rgw_state.json_text(desired, "notification", mapping_only=True, non_empty=True)
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        owner = common.optional_text(owner, "owner")
        old = _json_setting(
            "ceph_rgw_bucket.get_notifications",
            name,
            daemon_name,
            owner,
            profile,
            label="RGW bucket notifications",
        )
        if rgw_state.canonical(old) == rgw_state.canonical(desired):
            return reconcile.no_change(ret, f"RGW bucket {name} notifications are current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW bucket {name} notifications would be reconciled."
            )
        response = __salt__["ceph_rgw_bucket.set_notifications"](
            name,
            payload,
            daemon_name=daemon_name,
            owner=owner,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _json_setting(
            "ceph_rgw_bucket.get_notifications",
            name,
            daemon_name,
            owner,
            profile,
            label="RGW bucket notifications",
        )
        if rgw_state.canonical(after) != rgw_state.canonical(desired):
            raise ProtocolError(f"RGW bucket {name} notifications did not converge.")
        return reconcile.changed(
            ret, old, after, f"RGW bucket {name} notifications were reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def notifications_absent(
    name,
    daemon_name=None,
    owner=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure the complete current-Ceph bucket notification document is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        owner = common.optional_text(owner, "owner")
        confirm = common.boolean(confirm, "confirm")
        old = _json_setting(
            "ceph_rgw_bucket.get_notifications",
            name,
            daemon_name,
            owner,
            profile,
            label="RGW bucket notifications",
        )
        notification_ids = _notification_ids(old)
        if not notification_ids:
            return reconcile.no_change(ret, f"RGW bucket {name} notifications are already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, {}, f"RGW bucket {name} notifications would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting bucket notifications requires confirm=True.")
        for notification_id in notification_ids:
            response = __salt__["ceph_rgw_bucket.delete_notification"](
                name,
                notification_id,
                daemon_name=daemon_name,
                owner=owner,
                confirm=True,
                profile=profile,
            )
            _wait(response, profile, task_timeout, task_interval)
        after = _json_setting(
            "ceph_rgw_bucket.get_notifications",
            name,
            daemon_name,
            owner,
            profile,
            label="RGW bucket notifications",
        )
        if _notification_ids(after):
            raise ProtocolError(f"RGW bucket {name} notifications still exist.")
        return reconcile.changed(ret, old, {}, f"RGW bucket {name} notifications were deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _notification_ids(value):
    """Return every safely deletable ID from a full S3 notification document."""
    value = rgw_state.mapping(value, "RGW bucket notifications")
    collections = (
        "TopicConfigurations",
        "QueueConfigurations",
        "LambdaFunctionConfigurations",
    )
    unknown = [key for key, item in value.items() if key not in collections and item]
    if unknown:
        raise ProtocolError(
            "RGW bucket notifications contain unsupported non-empty fields: "
            f"{', '.join(sorted(unknown))}."
        )
    result = []
    for key in collections:
        items = value.get(key, [])
        if items in (None, ""):
            continue
        for item in rgw_state.list_of_mappings(items, f"RGW {key}"):
            identifier = item.get("Id", item.get("id"))
            if not isinstance(identifier, str) or not identifier:
                raise ProtocolError(f"RGW {key} entry omitted its deletion ID.")
            result.append(identifier)
    if len(result) != len(set(result)):
        raise ProtocolError("RGW bucket notifications contain duplicate deletion IDs.")
    return sorted(result)


def policy_present(
    name,
    policy,
    daemon_name=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure the bucket policy document is exact.

    Ceph's Dashboard controller has no public policy-delete operation, so an
    absent state is intentionally not exposed.
    """
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        desired = rgw_state.json_value(policy, "policy", mapping_only=True, non_empty=True)
        payload = rgw_state.json_text(desired, "policy", mapping_only=True, non_empty=True)
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        current = _bucket(name, daemon_name, profile)
        if current is None:
            raise ConfigurationError(f"RGW bucket {name} must exist before its policy.")
        old = rgw_state.json_value(current.get("bucket_policy") or {}, "bucket policy")
        if rgw_state.canonical(old) == rgw_state.canonical(desired):
            return reconcile.no_change(ret, f"RGW bucket {name} policy is current.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, old, desired, f"RGW bucket {name} policy would change.")
        response = __salt__["ceph_rgw_bucket.update_bucket"](
            name,
            _bucket_id(current),
            bucket_policy=payload,
            daemon_name=daemon_name,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after_resource = _bucket(name, daemon_name, profile)
        after = rgw_state.json_value(
            {} if after_resource is None else after_resource.get("bucket_policy") or {},
            "bucket policy",
        )
        if rgw_state.canonical(after) != rgw_state.canonical(desired):
            raise ProtocolError(f"RGW bucket {name} policy did not converge.")
        return reconcile.changed(ret, old, after, f"RGW bucket {name} policy was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _replication_view(current):
    value = current.get("replication")
    if isinstance(value, bool):
        return value
    value = rgw_state.mapping(value, "RGW bucket replication")
    for key in ("sync_policy_active", "replication_rules_configured"):
        if key not in value:
            raise ProtocolError("RGW bucket replication omitted a managed field.")
    return rgw_state.response_bool(
        value["sync_policy_active"], "sync_policy_active"
    ) or rgw_state.response_bool(
        value["replication_rules_configured"], "replication_rules_configured"
    )


def replication_present(
    name,
    enabled=True,
    daemon_name=None,
    confirm_disable=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure current-Ceph bucket replication is enabled or disabled."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket")
        enabled = common.boolean(enabled, "enabled")
        confirm_disable = common.boolean(confirm_disable, "confirm_disable")
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        current = _bucket(name, daemon_name, profile)
        if current is None:
            raise ConfigurationError(f"RGW bucket {name} must exist before replication is managed.")
        old = _replication_view(current)
        if old == enabled:
            return reconcile.no_change(ret, f"RGW bucket {name} replication is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, enabled, f"RGW bucket {name} replication would be reconciled."
            )
        if old and not enabled and not confirm_disable:
            raise ConfigurationError("Disabling bucket replication requires confirm_disable=True.")
        response = __salt__["ceph_rgw_bucket.update_bucket"](
            name,
            _bucket_id(current),
            replication=enabled,
            confirm_replication_disable=not enabled,
            daemon_name=daemon_name,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after_resource = _bucket(name, daemon_name, profile)
        after = None if after_resource is None else _replication_view(after_resource)
        if after != enabled:
            raise ProtocolError(f"RGW bucket {name} replication did not converge.")
        return reconcile.changed(ret, old, after, f"RGW bucket {name} replication was reconciled.")
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
    """Ensure a current-Ceph per-bucket rate limit is exact."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "bucket_id")
        confirm_disable = common.boolean(confirm_disable, "confirm_disable")
        desired = rgw_state.rate_desired(
            enabled, max_read_ops, max_write_ops, max_read_bytes, max_write_bytes
        )
        old = rgw_state.rate_view(
            reconcile.data(
                __salt__["ceph_rgw_bucket.get_rate_limit"](name, profile=profile),
                "RGW bucket rate limit",
                expected=Mapping,
            ),
            "bucket",
        )
        if old == desired:
            return reconcile.no_change(ret, f"RGW bucket rate limit for {name} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW bucket rate limit for {name} would be reconciled."
            )
        if old["enabled"] and not desired["enabled"] and not confirm_disable:
            raise ConfigurationError("Disabling an RGW rate limit requires confirm_disable=True.")
        response = __salt__["ceph_rgw_bucket.set_rate_limit"](name, profile=profile, **desired)
        _wait(response, profile, task_timeout, task_interval)
        after = rgw_state.rate_view(
            reconcile.data(
                __salt__["ceph_rgw_bucket.get_rate_limit"](name, profile=profile),
                "RGW bucket rate limit",
                expected=Mapping,
            ),
            "bucket",
        )
        if after != desired:
            raise ProtocolError(f"RGW bucket rate limit for {name} did not converge.")
        return reconcile.changed(
            ret, old, after, f"RGW bucket rate limit for {name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
