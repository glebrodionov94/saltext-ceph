"""Salt-facing composition for public RGW bucket controller operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rgw_bucket
from saltext.ceph.utils.ceph import rgw_common as common


def _call(operation, opts, pillar, context, profile, *args, **kwargs):
    client = ceph.get_client(opts, pillar, context, profile)
    return operation(client, *args, **kwargs).as_dict()


def list_buckets(opts, pillar, context, stats=False, daemon_name=None, uid=None, profile="default"):
    """List RGW buckets."""
    return _call(
        rgw_bucket.list_buckets,
        opts,
        pillar,
        context,
        profile,
        stats,
        daemon_name,
        uid,
    )


def get_bucket(opts, pillar, context, bucket, daemon_name=None, profile="default"):
    """Return one RGW bucket."""
    return _call(
        rgw_bucket.get_bucket,
        opts,
        pillar,
        context,
        profile,
        bucket,
        daemon_name,
    )


def create_bucket(
    opts,
    pillar,
    context,
    bucket,
    uid,
    zonegroup=None,
    placement_target=None,
    lock_enabled=False,
    lock_mode=None,
    lock_retention_period_days=None,
    lock_retention_period_years=None,
    encryption_state=False,
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
    return _call(
        rgw_bucket.create_bucket,
        opts,
        pillar,
        context,
        profile,
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
    )


def update_bucket(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_bucket.update_bucket,
        opts,
        pillar,
        context,
        profile,
        bucket,
        bucket_id,
        uid,
        versioning_state,
        encryption_state,
        encryption_type,
        key_id,
        mfa_delete,
        mfa_token_serial,
        common.secret_from_file(mfa_token_pin_source, "mfa_token_pin"),
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
    )


def delete_bucket(
    opts,
    pillar,
    context,
    bucket,
    daemon_name=None,
    confirm=False,
    profile="default",
):
    """Delete an empty RGW bucket after confirmation."""
    return _call(
        rgw_bucket.delete_bucket,
        opts,
        pillar,
        context,
        profile,
        bucket,
        daemon_name,
        confirm,
    )


def set_encryption_config(
    opts,
    pillar,
    context,
    encryption_type,
    kms_provider,
    config_source,
    daemon_name,
    reef_legacy=False,
    profile="default",
):
    """Set current structured or Reef legacy RGW encryption configuration."""
    return _call(
        rgw_bucket.set_encryption_config,
        opts,
        pillar,
        context,
        profile,
        encryption_type,
        kms_provider,
        common.secret_mapping_from_file(config_source, "config"),
        daemon_name,
        reef_legacy,
    )


def get_encryption(
    opts, pillar, context, bucket_name, daemon_name=None, owner=None, profile="default"
):
    """Return bucket encryption state."""
    return _call(
        rgw_bucket.get_encryption,
        opts,
        pillar,
        context,
        profile,
        bucket_name,
        daemon_name,
        owner,
    )


def delete_encryption(
    opts,
    pillar,
    context,
    bucket_name,
    daemon_name=None,
    owner=None,
    confirm=False,
    profile="default",
):
    """Delete bucket encryption after confirmation."""
    return _call(
        rgw_bucket.delete_encryption,
        opts,
        pillar,
        context,
        profile,
        bucket_name,
        daemon_name,
        owner,
        confirm,
    )


def get_encryption_config(
    opts,
    pillar,
    context,
    daemon_name=None,
    owner=None,
    include_secrets=False,
    profile="default",
):
    """Return encryption configuration with secrets redacted by default."""
    return _call(
        rgw_bucket.get_encryption_config,
        opts,
        pillar,
        context,
        profile,
        daemon_name,
        owner,
        include_secrets,
    )


def set_lifecycle(
    opts,
    pillar,
    context,
    bucket_name,
    lifecycle,
    daemon_name=None,
    owner=None,
    tenant=None,
    confirm_delete=False,
    profile="default",
):
    """Set a current-only bucket lifecycle policy."""
    return _call(
        rgw_bucket.set_lifecycle,
        opts,
        pillar,
        context,
        profile,
        bucket_name,
        lifecycle,
        daemon_name,
        owner,
        tenant,
        confirm_delete,
    )


def get_lifecycle(
    opts,
    pillar,
    context,
    bucket_name,
    daemon_name=None,
    owner=None,
    tenant=None,
    profile="default",
):
    """Return a current-only bucket lifecycle policy."""
    return _call(
        rgw_bucket.get_lifecycle,
        opts,
        pillar,
        context,
        profile,
        bucket_name,
        daemon_name,
        owner,
        tenant,
    )


def get_notifications(
    opts, pillar, context, bucket_name, daemon_name=None, owner=None, profile="default"
):
    """Return current-only bucket notifications."""
    return _call(
        rgw_bucket.get_notifications,
        opts,
        pillar,
        context,
        profile,
        bucket_name,
        daemon_name,
        owner,
    )


def set_notifications(
    opts,
    pillar,
    context,
    bucket_name,
    notification,
    daemon_name=None,
    owner=None,
    confirm_delete=False,
    profile="default",
):
    """Set current-only bucket notifications."""
    return _call(
        rgw_bucket.set_notifications,
        opts,
        pillar,
        context,
        profile,
        bucket_name,
        notification,
        daemon_name,
        owner,
        confirm_delete,
    )


def delete_notification(
    opts,
    pillar,
    context,
    bucket_name,
    notification_id,
    daemon_name=None,
    owner=None,
    confirm=False,
    profile="default",
):
    """Delete a current-only bucket notification after confirmation."""
    return _call(
        rgw_bucket.delete_notification,
        opts,
        pillar,
        context,
        profile,
        bucket_name,
        notification_id,
        daemon_name,
        owner,
        confirm,
    )


def get_global_rate_limit(opts, pillar, context, profile="default"):
    """Return current-only global bucket rate limits."""
    return _call(rgw_bucket.get_global_rate_limit, opts, pillar, context, profile)


def get_rate_limit(opts, pillar, context, bucket_id, profile="default"):
    """Return a current-only per-bucket rate limit."""
    return _call(
        rgw_bucket.get_rate_limit,
        opts,
        pillar,
        context,
        profile,
        bucket_id,
    )


def set_rate_limit(
    opts,
    pillar,
    context,
    bucket_id,
    enabled,
    max_read_ops,
    max_write_ops,
    max_read_bytes,
    max_write_bytes,
    profile="default",
):
    """Set a current-only per-bucket rate limit."""
    return _call(
        rgw_bucket.set_rate_limit,
        opts,
        pillar,
        context,
        profile,
        bucket_id,
        enabled,
        max_read_ops,
        max_write_ops,
        max_read_bytes,
        max_write_bytes,
    )
