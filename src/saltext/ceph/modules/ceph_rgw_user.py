"""Manage public Ceph Dashboard RGW user operations."""

from saltext.ceph.utils.ceph import rgw_user_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rgw_user"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, *args)


def list_users(daemon_name=None, detailed=False, include_secrets=False, profile="default"):
    """List RGW users.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.list_users
    """
    return _invoke(rgw_user_api.list_users, daemon_name, detailed, include_secrets, profile)


def get_user(uid, daemon_name=None, stats=True, include_secrets=False, profile="default"):
    """Return one RGW user.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.get_user uid
    """
    return _invoke(rgw_user_api.get_user, uid, daemon_name, stats, include_secrets, profile)


def get_emails(daemon_name=None, profile="default"):
    """List RGW user email addresses.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.get_emails
    """
    return _invoke(rgw_user_api.get_emails, daemon_name, profile)


def create_user(
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
    """Create an RGW user.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.create_user uid display_name
    """
    return _invoke(
        rgw_user_api.create_user,
        uid,
        display_name,
        email,
        max_buckets,
        system,
        suspended,
        generate_key,
        access_key_source,
        secret_key_source,
        daemon_name,
        account_id,
        account_root_user,
        account_policies,
        confirm_policy_detach,
        include_secrets,
        profile,
    )


def update_user(
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
    """Update an RGW user.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.update_user uid
    """
    return _invoke(
        rgw_user_api.update_user,
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
        profile,
    )


def delete_user(uid, daemon_name=None, confirm=False, profile="default"):
    """Delete an RGW user after confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.delete_user uid
    """
    return _invoke(rgw_user_api.delete_user, uid, daemon_name, confirm, profile)


def create_capability(uid, capability_type, permission, daemon_name=None, profile="default"):
    """Add an Admin Ops capability.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.create_capability uid capability_type permission
    """
    return _invoke(
        rgw_user_api.create_capability, uid, capability_type, permission, daemon_name, profile
    )


def delete_capability(
    uid, capability_type, permission, daemon_name=None, confirm=False, profile="default"
):
    """Delete an Admin Ops capability after confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.delete_capability uid capability_type permission
    """
    return _invoke(
        rgw_user_api.delete_capability,
        uid,
        capability_type,
        permission,
        daemon_name,
        confirm,
        profile,
    )


def create_key(
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
    """Create an RGW user key.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.create_key uid
    """
    return _invoke(
        rgw_user_api.create_key,
        uid,
        key_type,
        subuser,
        generate_key,
        access_key_source,
        secret_key_source,
        daemon_name,
        include_secrets,
        profile,
    )


def delete_key(
    uid,
    key_type="s3",
    subuser=None,
    access_key_source=None,
    daemon_name=None,
    confirm=False,
    profile="default",
):
    """Delete an RGW user key after confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.delete_key uid
    """
    return _invoke(
        rgw_user_api.delete_key,
        uid,
        key_type,
        subuser,
        access_key_source,
        daemon_name,
        confirm,
        profile,
    )


def get_quota(uid, daemon_name=None, profile="default"):
    """Return an RGW user quota.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.get_quota uid
    """
    return _invoke(rgw_user_api.get_quota, uid, daemon_name, profile)


def set_quota(
    uid, quota_type, enabled, max_size_kb, max_objects, daemon_name=None, profile="default"
):
    """Set an RGW user quota.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.set_quota uid quota_type enabled max_size_kb max_objects
    """
    return _invoke(
        rgw_user_api.set_quota,
        uid,
        quota_type,
        enabled,
        max_size_kb,
        max_objects,
        daemon_name,
        profile,
    )


def create_subuser(
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
    """Create or update an RGW subuser.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.create_subuser uid subuser access
    """
    return _invoke(
        rgw_user_api.create_subuser,
        uid,
        subuser,
        access,
        key_type,
        generate_secret,
        access_key_source,
        secret_key_source,
        daemon_name,
        include_secrets,
        profile,
    )


def delete_subuser(
    uid, subuser, purge_keys=True, daemon_name=None, confirm=False, profile="default"
):
    """Delete an RGW subuser after confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.delete_subuser uid subuser
    """
    return _invoke(
        rgw_user_api.delete_subuser, uid, subuser, purge_keys, daemon_name, confirm, profile
    )


def get_global_rate_limit(profile="default"):
    """Return current-only global user rate limits.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.get_global_rate_limit
    """
    return _invoke(rgw_user_api.get_global_rate_limit, profile)


def get_rate_limit(uid, profile="default"):
    """Return a current-only user rate limit.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.get_rate_limit uid
    """
    return _invoke(rgw_user_api.get_rate_limit, uid, profile)


def set_rate_limit(
    uid,
    enabled=False,
    max_read_ops=0,
    max_write_ops=0,
    max_read_bytes=0,
    max_write_bytes=0,
    profile="default",
):
    """Set a current-only user rate limit.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_rgw_user.set_rate_limit uid
    """
    return _invoke(
        rgw_user_api.set_rate_limit,
        uid,
        enabled,
        max_read_ops,
        max_write_ops,
        max_read_bytes,
        max_write_bytes,
        profile,
    )
