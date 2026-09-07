"""Salt-facing composition for public RGW roles and current-only accounts."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rgw_iam


def _call(operation, opts, pillar, context, profile, *args, **kwargs):
    client = ceph.get_client(opts, pillar, context, profile)
    return operation(client, *args, **kwargs).as_dict()


def list_roles(opts, pillar, context, account_id=None, profile="default"):
    """List Reef global or current account-scoped roles."""
    return _call(rgw_iam.list_roles, opts, pillar, context, profile, account_id)


def get_role(opts, pillar, context, account_id, role_name, profile="default"):
    """Return a current account-scoped role."""
    return _call(rgw_iam.get_role, opts, pillar, context, profile, account_id, role_name)


def create_role(
    opts,
    pillar,
    context,
    role_name,
    role_path,
    role_assume_policy_doc="",
    account_id=None,
    profile="default",
):
    """Create a Reef global or current account-scoped role."""
    return _call(
        rgw_iam.create_role,
        opts,
        pillar,
        context,
        profile,
        role_name,
        role_path,
        role_assume_policy_doc,
        account_id,
    )


def update_role(
    opts,
    pillar,
    context,
    role_name,
    max_session_duration,
    account_id=None,
    profile="default",
):
    """Update a Reef global or current account-scoped role."""
    return _call(
        rgw_iam.update_role,
        opts,
        pillar,
        context,
        profile,
        role_name,
        max_session_duration,
        account_id,
    )


def delete_role(
    opts,
    pillar,
    context,
    role_name,
    account_id=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW role after confirmation."""
    return _call(
        rgw_iam.delete_role,
        opts,
        pillar,
        context,
        profile,
        role_name,
        account_id,
        confirm,
    )


def create_account(
    opts,
    pillar,
    context,
    account_name,
    tenant=None,
    email=None,
    max_buckets=None,
    max_users=None,
    max_roles=None,
    max_groups=None,
    max_access_keys=None,
    daemon_name=None,
    profile="default",
):
    """Create a current-only RGW account."""
    return _call(
        rgw_iam.create_account,
        opts,
        pillar,
        context,
        profile,
        account_name,
        tenant,
        email,
        max_buckets,
        max_users,
        max_roles,
        max_groups,
        max_access_keys,
        daemon_name,
    )


def list_accounts(opts, pillar, context, daemon_name=None, detailed=False, profile="default"):
    """List current-only RGW accounts."""
    return _call(
        rgw_iam.list_accounts,
        opts,
        pillar,
        context,
        profile,
        daemon_name,
        detailed,
    )


def get_account(opts, pillar, context, account_id, daemon_name=None, profile="default"):
    """Return one current-only RGW account."""
    return _call(
        rgw_iam.get_account,
        opts,
        pillar,
        context,
        profile,
        account_id,
        daemon_name,
    )


def account_exists(opts, pillar, context, account_name, daemon_name=None, profile="default"):
    """Check whether a current-only account exists."""
    return _call(
        rgw_iam.account_exists,
        opts,
        pillar,
        context,
        profile,
        account_name,
        daemon_name,
    )


def update_account(
    opts,
    pillar,
    context,
    account_id,
    account_name,
    email=None,
    tenant=None,
    max_buckets=None,
    max_users=None,
    max_roles=None,
    max_groups=None,
    max_access_keys=None,
    daemon_name=None,
    profile="default",
):
    """Update a current-only RGW account."""
    return _call(
        rgw_iam.update_account,
        opts,
        pillar,
        context,
        profile,
        account_id,
        account_name,
        email,
        tenant,
        max_buckets,
        max_users,
        max_roles,
        max_groups,
        max_access_keys,
        daemon_name,
    )


def delete_account(
    opts,
    pillar,
    context,
    account_id,
    daemon_name=None,
    confirm=False,
    profile="default",
):
    """Delete a current-only RGW account after confirmation."""
    return _call(
        rgw_iam.delete_account,
        opts,
        pillar,
        context,
        profile,
        account_id,
        daemon_name,
        confirm,
    )


def set_account_quota(
    opts,
    pillar,
    context,
    account_id,
    quota_type,
    max_size,
    max_objects,
    enabled,
    profile="default",
):
    """Set a current-only RGW account quota."""
    return _call(
        rgw_iam.set_account_quota,
        opts,
        pillar,
        context,
        profile,
        account_id,
        quota_type,
        max_size,
        max_objects,
        enabled,
    )


def set_account_quota_status(
    opts,
    pillar,
    context,
    account_id,
    quota_type,
    quota_status,
    profile="default",
):
    """Enable or disable a current-only RGW account quota."""
    return _call(
        rgw_iam.set_account_quota_status,
        opts,
        pillar,
        context,
        profile,
        account_id,
        quota_type,
        quota_status,
    )
