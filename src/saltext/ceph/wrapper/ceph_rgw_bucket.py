"""Manage RGW bucket operations from salt-ssh."""

from saltext.ceph.utils.ceph import rgw_bucket_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rgw_bucket"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_buckets(stats=False, daemon_name=None, uid=None, profile="default"):
    """List RGW buckets."""
    return _invoke(rgw_bucket_api.list_buckets, stats, daemon_name, uid, profile)


def get_bucket(bucket, daemon_name=None, profile="default"):
    """Return one RGW bucket."""
    return _invoke(rgw_bucket_api.get_bucket, bucket, daemon_name, profile)


def create_bucket(
    bucket,
    uid,
    zonegroup=None,
    placement_target=None,
    lock_enabled=False,
    lock_mode=None,
    lock_retention_period_days=None,
    lock_retention_period_years=None,
    encryption_state=None,
    encryption_type=None,
    key_id=None,
    tags=None,
    bucket_policy=None,
    canned_acl=None,
    replication=None,
    daemon_name=None,
    profile="default",
):
    """Create an RGW bucket."""
    return _invoke(
        rgw_bucket_api.create_bucket,
        bucket,
        uid,
        zonegroup,
        placement_target,
        lock_enabled,
        lock_mode,
        lock_retention_period_days,
        lock_retention_period_years,
        encryption_state,
        encryption_type,
        key_id,
        tags,
        bucket_policy,
        canned_acl,
        replication,
        daemon_name,
        profile,
    )


def update_bucket(
    bucket,
    bucket_id,
    uid=None,
    versioning_state=None,
    encryption_state=None,
    encryption_type=None,
    key_id=None,
    mfa_delete=None,
    mfa_token_serial=None,
    mfa_token_pin_source=None,
    lock_mode=None,
    lock_retention_period_days=None,
    lock_retention_period_years=None,
    tags=None,
    bucket_policy=None,
    canned_acl=None,
    replication=None,
    lifecycle=None,
    daemon_name=None,
    confirm_lifecycle_delete=False,
    confirm_encryption_disable=False,
    confirm_replication_disable=False,
    profile="default",
):
    """Update an RGW bucket."""
    return _invoke(
        rgw_bucket_api.update_bucket,
        bucket,
        bucket_id,
        uid,
        versioning_state,
        encryption_state,
        encryption_type,
        key_id,
        mfa_delete,
        mfa_token_serial,
        mfa_token_pin_source,
        lock_mode,
        lock_retention_period_days,
        lock_retention_period_years,
        tags,
        bucket_policy,
        canned_acl,
        replication,
        lifecycle,
        daemon_name,
        confirm_lifecycle_delete,
        confirm_encryption_disable,
        confirm_replication_disable,
        profile,
    )


def delete_bucket(bucket, daemon_name=None, confirm=False, profile="default"):
    """Delete an empty RGW bucket after confirmation."""
    return _invoke(rgw_bucket_api.delete_bucket, bucket, daemon_name, confirm, profile)


def set_encryption_config(
    encryption_type, kms_provider, config_source, daemon_name, reef_legacy=False, profile="default"
):
    """Set current structured or Reef legacy RGW encryption configuration."""
    return _invoke(
        rgw_bucket_api.set_encryption_config,
        encryption_type,
        kms_provider,
        config_source,
        daemon_name,
        reef_legacy,
        profile,
    )


def get_encryption(bucket_name, daemon_name=None, owner=None, profile="default"):
    """Return bucket encryption state."""
    return _invoke(rgw_bucket_api.get_encryption, bucket_name, daemon_name, owner, profile)


def delete_encryption(bucket_name, daemon_name=None, owner=None, confirm=False, profile="default"):
    """Delete bucket encryption after confirmation."""
    return _invoke(
        rgw_bucket_api.delete_encryption, bucket_name, daemon_name, owner, confirm, profile
    )


def get_encryption_config(daemon_name=None, owner=None, include_secrets=False, profile="default"):
    """Return encryption configuration with secrets redacted by default."""
    return _invoke(
        rgw_bucket_api.get_encryption_config, daemon_name, owner, include_secrets, profile
    )


def set_lifecycle(
    bucket_name,
    lifecycle,
    daemon_name=None,
    owner=None,
    tenant=None,
    confirm_delete=False,
    profile="default",
):
    """Set a current-only bucket lifecycle policy."""
    return _invoke(
        rgw_bucket_api.set_lifecycle,
        bucket_name,
        lifecycle,
        daemon_name,
        owner,
        tenant,
        confirm_delete,
        profile,
    )


def get_lifecycle(bucket_name, daemon_name=None, owner=None, tenant=None, profile="default"):
    """Return a current-only bucket lifecycle policy."""
    return _invoke(rgw_bucket_api.get_lifecycle, bucket_name, daemon_name, owner, tenant, profile)


def get_notifications(bucket_name, daemon_name=None, owner=None, profile="default"):
    """Return current-only bucket notifications."""
    return _invoke(rgw_bucket_api.get_notifications, bucket_name, daemon_name, owner, profile)


def set_notifications(
    bucket_name,
    notification,
    daemon_name=None,
    owner=None,
    confirm_delete=False,
    profile="default",
):
    """Set current-only bucket notifications."""
    return _invoke(
        rgw_bucket_api.set_notifications,
        bucket_name,
        notification,
        daemon_name,
        owner,
        confirm_delete,
        profile,
    )


def delete_notification(
    bucket_name, notification_id, daemon_name=None, owner=None, confirm=False, profile="default"
):
    """Delete a current-only bucket notification after confirmation."""
    return _invoke(
        rgw_bucket_api.delete_notification,
        bucket_name,
        notification_id,
        daemon_name,
        owner,
        confirm,
        profile,
    )


def get_global_rate_limit(profile="default"):
    """Return current-only global bucket rate limits."""
    return _invoke(rgw_bucket_api.get_global_rate_limit, profile)


def get_rate_limit(bucket_id, profile="default"):
    """Return a current-only per-bucket rate limit."""
    return _invoke(rgw_bucket_api.get_rate_limit, bucket_id, profile)


def set_rate_limit(
    bucket_id,
    enabled,
    max_read_ops,
    max_write_ops,
    max_read_bytes,
    max_write_bytes,
    profile="default",
):
    """Set a current-only per-bucket rate limit."""
    return _invoke(
        rgw_bucket_api.set_rate_limit,
        bucket_id,
        enabled,
        max_read_ops,
        max_write_ops,
        max_read_bytes,
        max_write_bytes,
        profile,
    )
