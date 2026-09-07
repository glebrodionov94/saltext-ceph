"""Salt-facing composition for public RGW user controller operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph import rgw_user


def _call(operation, opts, pillar, context, profile, *args, **kwargs):
    client = ceph.get_client(opts, pillar, context, profile)
    return operation(client, *args, **kwargs).as_dict()


def list_users(
    opts,
    pillar,
    context,
    daemon_name=None,
    detailed=False,
    include_secrets=False,
    profile="default",
):
    """List RGW users."""
    return _call(
        rgw_user.list_users,
        opts,
        pillar,
        context,
        profile,
        daemon_name,
        detailed,
        include_secrets,
    )


def get_user(
    opts,
    pillar,
    context,
    uid,
    daemon_name=None,
    stats=True,
    include_secrets=False,
    profile="default",
):
    """Return one RGW user."""
    return _call(
        rgw_user.get_user,
        opts,
        pillar,
        context,
        profile,
        uid,
        daemon_name,
        stats,
        include_secrets,
    )


def get_emails(opts, pillar, context, daemon_name=None, profile="default"):
    """List RGW user email addresses."""
    return _call(rgw_user.get_emails, opts, pillar, context, profile, daemon_name)


def create_user(
    opts,
    pillar,
    context,
    uid,
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
    account_root_user=False,
    account_policies=None,
    confirm_policy_detach=False,
    include_secrets=False,
    profile="default",
):
    """Create an RGW user."""
    return _call(
        rgw_user.create_user,
        opts,
        pillar,
        context,
        profile,
        uid,
        display_name,
        email,
        max_buckets,
        system,
        suspended,
        generate_key,
        common.secret_from_file(access_key_source, "access_key"),
        common.secret_from_file(secret_key_source, "secret_key"),
        daemon_name,
        account_id,
        account_root_user,
        account_policies,
        confirm_policy_detach,
        include_secrets,
    )


def update_user(
    opts,
    pillar,
    context,
    uid,
    display_name=None,
    email=None,
    max_buckets=None,
    system=None,
    suspended=None,
    daemon_name=None,
    account_id=None,
    account_root_user=False,
    account_policies=None,
    confirm_policy_detach=False,
    include_secrets=False,
    profile="default",
):
    """Update an RGW user."""
    return _call(
        rgw_user.update_user,
        opts,
        pillar,
        context,
        profile,
        uid,
        display_name,
        email,
        max_buckets,
        system,
        suspended,
        daemon_name,
        account_id,
        account_root_user,
        account_policies,
        confirm_policy_detach,
        include_secrets,
    )


def delete_user(
    opts,
    pillar,
    context,
    uid,
    daemon_name=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW user after confirmation."""
    return _call(
        rgw_user.delete_user,
        opts,
        pillar,
        context,
        profile,
        uid,
        daemon_name,
        confirm,
    )


def create_capability(
    opts,
    pillar,
    context,
    uid,
    capability_type,
    permission,
    daemon_name=None,
    profile="default",
):
    """Add an Admin Ops capability."""
    return _call(
        rgw_user.create_capability,
        opts,
        pillar,
        context,
        profile,
        uid,
        capability_type,
        permission,
        daemon_name,
    )


def delete_capability(
    opts,
    pillar,
    context,
    uid,
    capability_type,
    permission,
    daemon_name=None,
    confirm=False,
    profile="default",
):
    """Delete an Admin Ops capability after confirmation."""
    return _call(
        rgw_user.delete_capability,
        opts,
        pillar,
        context,
        profile,
        uid,
        capability_type,
        permission,
        daemon_name,
        confirm,
    )


def create_key(
    opts,
    pillar,
    context,
    uid,
    key_type="s3",
    subuser=None,
    generate_key=True,
    access_key_source=None,
    secret_key_source=None,
    daemon_name=None,
    include_secrets=False,
    profile="default",
):
    """Create an RGW user key."""
    return _call(
        rgw_user.create_key,
        opts,
        pillar,
        context,
        profile,
        uid,
        key_type,
        subuser,
        generate_key,
        common.secret_from_file(access_key_source, "access_key"),
        common.secret_from_file(secret_key_source, "secret_key"),
        daemon_name,
        include_secrets,
    )


def delete_key(
    opts,
    pillar,
    context,
    uid,
    key_type="s3",
    subuser=None,
    access_key_source=None,
    daemon_name=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW user key after confirmation."""
    return _call(
        rgw_user.delete_key,
        opts,
        pillar,
        context,
        profile,
        uid,
        key_type,
        subuser,
        common.secret_from_file(access_key_source, "access_key"),
        daemon_name,
        confirm,
    )


def get_quota(opts, pillar, context, uid, daemon_name=None, profile="default"):
    """Return an RGW user quota."""
    return _call(rgw_user.get_quota, opts, pillar, context, profile, uid, daemon_name)


def set_quota(
    opts,
    pillar,
    context,
    uid,
    quota_type,
    enabled,
    max_size_kb,
    max_objects,
    daemon_name=None,
    profile="default",
):
    """Set an RGW user quota."""
    return _call(
        rgw_user.set_quota,
        opts,
        pillar,
        context,
        profile,
        uid,
        quota_type,
        enabled,
        max_size_kb,
        max_objects,
        daemon_name,
    )


def create_subuser(
    opts,
    pillar,
    context,
    uid,
    subuser,
    access,
    key_type="s3",
    generate_secret=True,
    access_key_source=None,
    secret_key_source=None,
    daemon_name=None,
    include_secrets=False,
    profile="default",
):
    """Create or update an RGW subuser."""
    return _call(
        rgw_user.create_subuser,
        opts,
        pillar,
        context,
        profile,
        uid,
        subuser,
        access,
        key_type,
        generate_secret,
        common.secret_from_file(access_key_source, "access_key"),
        common.secret_from_file(secret_key_source, "secret_key"),
        daemon_name,
        include_secrets,
    )


def delete_subuser(
    opts,
    pillar,
    context,
    uid,
    subuser,
    purge_keys=True,
    daemon_name=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW subuser after confirmation."""
    return _call(
        rgw_user.delete_subuser,
        opts,
        pillar,
        context,
        profile,
        uid,
        subuser,
        purge_keys,
        daemon_name,
        confirm,
    )


def get_global_rate_limit(opts, pillar, context, profile="default"):
    """Return current-only global user rate limits."""
    return _call(rgw_user.get_global_rate_limit, opts, pillar, context, profile)


def get_rate_limit(opts, pillar, context, uid, profile="default"):
    """Return a current-only user rate limit."""
    return _call(rgw_user.get_rate_limit, opts, pillar, context, profile, uid)


def set_rate_limit(
    opts,
    pillar,
    context,
    uid,
    enabled=False,
    max_read_ops=0,
    max_write_ops=0,
    max_read_bytes=0,
    max_write_bytes=0,
    profile="default",
):
    """Set a current-only user rate limit."""
    return _call(
        rgw_user.set_rate_limit,
        opts,
        pillar,
        context,
        profile,
        uid,
        enabled,
        max_read_ops,
        max_write_ops,
        max_read_bytes,
        max_write_bytes,
    )
