"""Manage RGW iam operations from salt-ssh."""

from saltext.ceph.utils.ceph import rgw_iam_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rgw_iam"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_roles(account_id=None, profile="default"):
    """List Reef global or current account-scoped roles."""
    return _invoke(rgw_iam_api.list_roles, account_id, profile)


def get_role(account_id, role_name, profile="default"):
    """Return a current account-scoped role."""
    return _invoke(rgw_iam_api.get_role, account_id, role_name, profile)


def create_role(
    role_name, role_path, role_assume_policy_doc="", account_id=None, profile="default"
):
    """Create a Reef global or current account-scoped role."""
    return _invoke(
        rgw_iam_api.create_role, role_name, role_path, role_assume_policy_doc, account_id, profile
    )


def update_role(role_name, max_session_duration, account_id=None, profile="default"):
    """Update a Reef global or current account-scoped role."""
    return _invoke(rgw_iam_api.update_role, role_name, max_session_duration, account_id, profile)


def delete_role(role_name, account_id=None, confirm=False, profile="default"):
    """Delete an RGW role after confirmation."""
    return _invoke(rgw_iam_api.delete_role, role_name, account_id, confirm, profile)


def create_account(
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
    return _invoke(
        rgw_iam_api.create_account,
        account_name,
        tenant,
        email,
        max_buckets,
        max_users,
        max_roles,
        max_groups,
        max_access_keys,
        daemon_name,
        profile,
    )


def list_accounts(daemon_name=None, detailed=False, profile="default"):
    """List current-only RGW accounts."""
    return _invoke(rgw_iam_api.list_accounts, daemon_name, detailed, profile)


def get_account(account_id, daemon_name=None, profile="default"):
    """Return one current-only RGW account."""
    return _invoke(rgw_iam_api.get_account, account_id, daemon_name, profile)


def account_exists(account_name, daemon_name=None, profile="default"):
    """Check whether a current-only account exists."""
    return _invoke(rgw_iam_api.account_exists, account_name, daemon_name, profile)


def update_account(
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
    return _invoke(
        rgw_iam_api.update_account,
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
        profile,
    )


def delete_account(account_id, daemon_name=None, confirm=False, profile="default"):
    """Delete a current-only RGW account after confirmation."""
    return _invoke(rgw_iam_api.delete_account, account_id, daemon_name, confirm, profile)


def set_account_quota(account_id, quota_type, max_size, max_objects, enabled, profile="default"):
    """Set a current-only RGW account quota."""
    return _invoke(
        rgw_iam_api.set_account_quota,
        account_id,
        quota_type,
        max_size,
        max_objects,
        enabled,
        profile,
    )


def set_account_quota_status(account_id, quota_type, quota_status, profile="default"):
    """Enable or disable a current-only RGW account quota."""
    return _invoke(
        rgw_iam_api.set_account_quota_status, account_id, quota_type, quota_status, profile
    )
