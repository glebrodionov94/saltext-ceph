"""Public Ceph Dashboard RGW user controller operations."""

from collections.abc import Mapping

from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/rgw/user"


def _daemon(value):
    return common.optional_text(value, "daemon_name")


def _optional_bool(value, label):
    return None if value is None else common.boolean(value, label)


def _optional_limit(value, label):
    return None if value is None else common.integer(value, label)


def _key_type(value):
    value = common.name(value, "key_type").lower()
    if value not in ("s3", "swift"):
        raise ConfigurationError("key_type must be s3 or swift.")
    return value


def _list_result(response, detailed, include_secrets):
    if not isinstance(response.data, list):
        raise ProtocolError("RGW user list returned an unexpected response shape.")
    expected = Mapping if detailed else str
    if not all(isinstance(item, expected) for item in response.data):
        raise ProtocolError("RGW user list returned an unexpected response shape.")
    return common.safe_response(response, "RGW user list", include_secrets=include_secrets)


def list_users(client, daemon_name=None, detailed=False, include_secrets=False):
    """List user IDs, or detailed users on current Ceph, with secrets redacted."""
    detailed = common.boolean(detailed, "detailed")
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request(
        "GET",
        RESOURCE_PATH,
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name), detailed=True if detailed else None),
    )
    return _list_result(response, detailed, include_secrets)


def get_user(client, uid, daemon_name=None, stats=True, include_secrets=False):
    """Return one RGW user, redacting S3 and Swift credentials by default."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}",
        api_version=API_VERSION,
        params=common.params(
            daemon_name=_daemon(daemon_name), stats=common.boolean(stats, "stats")
        ),
    )
    return common.safe_response(
        response, "RGW user", shape="mapping", include_secrets=include_secrets
    )


def get_emails(client, daemon_name=None):
    """List non-empty RGW user email addresses."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/get_emails",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name)),
    )
    if not isinstance(response.data, list) or not all(
        isinstance(item, str) for item in response.data
    ):
        raise ProtocolError("RGW user email list returned an unexpected response shape.")
    return common.safe_response(response, "RGW user email list", shape="list")


def _account_policies(value, confirm_detach=False):
    if value is None:
        return None
    value = common.mapping(value, "account_policies", required=False)
    if set(value) - {"attach", "detach"}:
        raise ConfigurationError("account_policies contains unsupported fields.")
    for action, policies in value.items():
        value[action] = common.string_list(policies, f"account_policies {action}")
    if value.get("detach"):
        common.confirm(confirm_detach)
    return value


def create_user(
    client,
    uid,
    display_name,
    email=None,
    max_buckets=None,
    system=None,
    suspended=None,
    generate_key=None,
    access_key=None,
    secret_key=None,
    daemon_name=None,
    account_id=None,
    account_root_user=False,
    account_policies=None,
    confirm_policy_detach=False,
    include_secrets=False,
):
    """Create a user; account fields are current-only and credentials are redacted."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    data = common.params(
        uid=common.name(uid, "uid"),
        display_name=common.name(display_name, "display_name"),
        email=common.optional_text(email, "email"),
        max_buckets=_optional_limit(max_buckets, "max_buckets"),
        system=_optional_bool(system, "system"),
        suspended=_optional_bool(suspended, "suspended"),
        generate_key=_optional_bool(generate_key, "generate_key"),
        access_key=common.optional_text(access_key, "access_key"),
        secret_key=common.optional_text(secret_key, "secret_key"),
        daemon_name=_daemon(daemon_name),
        account_id=common.optional_text(account_id, "account_id"),
        account_root_user=True if common.boolean(account_root_user, "account_root_user") else None,
        account_policies=_account_policies(account_policies, confirm_policy_detach),
    )
    response = client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)
    return common.safe_response(response, "RGW user creation", include_secrets=include_secrets)


def update_user(
    client,
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
):
    """Update an RGW user, including optional current-only account membership."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    data = common.params(
        display_name=common.optional_text(display_name, "display_name"),
        email=common.optional_text(email, "email"),
        max_buckets=_optional_limit(max_buckets, "max_buckets"),
        system=_optional_bool(system, "system"),
        suspended=_optional_bool(suspended, "suspended"),
        daemon_name=_daemon(daemon_name),
        account_id=common.optional_text(account_id, "account_id"),
        account_root_user=True if common.boolean(account_root_user, "account_root_user") else None,
        account_policies=_account_policies(account_policies, confirm_policy_detach),
    )
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}",
        api_version=API_VERSION,
        data=data,
    )
    return common.safe_response(response, "RGW user update", include_secrets=include_secrets)


def delete_user(client, uid, daemon_name=None, confirm=False):
    """Delete an RGW user after explicit confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name)),
    )
    return common.safe_response(response, "RGW user deletion")


def create_capability(client, uid, capability_type, permission, daemon_name=None):
    """Add an Admin Ops capability to a user."""
    response = client.request(
        "POST",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/capability",
        api_version=API_VERSION,
        data=common.params(
            type=common.name(capability_type, "capability_type"),
            perm=common.name(permission, "permission"),
            daemon_name=_daemon(daemon_name),
        ),
    )
    return common.safe_response(response, "RGW user capability creation")


def delete_capability(client, uid, capability_type, permission, daemon_name=None, confirm=False):
    """Delete a user capability after explicit confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/capability",
        api_version=API_VERSION,
        params=common.params(
            type=common.name(capability_type, "capability_type"),
            perm=common.name(permission, "permission"),
            daemon_name=_daemon(daemon_name),
        ),
    )
    return common.safe_response(response, "RGW user capability deletion")


def create_key(
    client,
    uid,
    key_type="s3",
    subuser=None,
    generate_key=True,
    access_key=None,
    secret_key=None,
    daemon_name=None,
    include_secrets=False,
):
    """Create an S3 or Swift key, returning credentials only with opt-in."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    key_type = _key_type(key_type)
    response = client.request(
        "POST",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/key",
        api_version=API_VERSION,
        data=common.params(
            key_type=key_type,
            subuser=common.optional_text(subuser, "subuser"),
            generate_key=common.boolean(generate_key, "generate_key"),
            access_key=common.optional_text(access_key, "access_key"),
            secret_key=common.optional_text(secret_key, "secret_key"),
            daemon_name=_daemon(daemon_name),
        ),
    )
    return common.safe_response(response, "RGW user key creation", include_secrets=include_secrets)


def delete_key(
    client,
    uid,
    key_type="s3",
    subuser=None,
    access_key=None,
    daemon_name=None,
    confirm=False,
):
    """Delete an S3 or Swift key after explicit confirmation."""
    common.confirm(confirm)
    key_type = _key_type(key_type)
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/key",
        api_version=API_VERSION,
        params=common.params(
            key_type=key_type,
            subuser=common.optional_text(subuser, "subuser"),
            access_key=common.optional_text(access_key, "access_key"),
            daemon_name=_daemon(daemon_name),
        ),
    )
    return common.safe_response(response, "RGW user key deletion")


def get_quota(client, uid, daemon_name=None):
    """Return an RGW user's user and bucket quotas."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/quota",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name)),
    )
    return common.safe_response(response, "RGW user quota", shape="mapping")


def set_quota(client, uid, quota_type, enabled, max_size_kb, max_objects, daemon_name=None):
    """Set an RGW user's user or bucket quota."""
    quota_type = common.name(quota_type, "quota_type")
    if quota_type not in ("user", "bucket"):
        raise ConfigurationError("quota_type must be user or bucket.")
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/quota",
        api_version=API_VERSION,
        data=common.params(
            quota_type=quota_type,
            enabled=common.boolean(enabled, "enabled"),
            max_size_kb=common.integer(max_size_kb, "max_size_kb"),
            max_objects=common.integer(max_objects, "max_objects"),
            daemon_name=_daemon(daemon_name),
        ),
    )
    return common.response_copy(response, "RGW user quota update")


def create_subuser(
    client,
    uid,
    subuser,
    access,
    key_type="s3",
    generate_secret=True,
    access_key=None,
    secret_key=None,
    daemon_name=None,
    include_secrets=False,
):
    """Create or update a subuser, returning generated keys only with opt-in."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    access = common.name(access, "access").lower()
    if access not in ("read", "write", "readwrite", "full"):
        raise ConfigurationError("access must be read, write, readwrite, or full.")
    response = client.request(
        "POST",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/subuser",
        api_version=API_VERSION,
        data=common.params(
            subuser=common.name(subuser, "subuser"),
            access=access,
            key_type=_key_type(key_type),
            generate_secret=common.boolean(generate_secret, "generate_secret"),
            access_key=common.optional_text(access_key, "access_key"),
            secret_key=common.optional_text(secret_key, "secret_key"),
            daemon_name=_daemon(daemon_name),
        ),
    )
    return common.safe_response(response, "RGW subuser creation", include_secrets=include_secrets)


def delete_subuser(client, uid, subuser, purge_keys=True, daemon_name=None, confirm=False):
    """Delete an RGW subuser after explicit confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/subuser/"
        f"{common.segment(subuser, 'subuser')}",
        api_version=API_VERSION,
        params=common.params(
            purge_keys=common.boolean(purge_keys, "purge_keys"),
            daemon_name=_daemon(daemon_name),
        ),
    )
    return common.safe_response(response, "RGW subuser deletion")


def get_global_rate_limit(client):
    """Return the current-only global RGW user rate limit."""
    response = client.request("GET", f"{RESOURCE_PATH}/ratelimit", api_version=API_VERSION)
    return common.safe_response(response, "RGW global user rate limit", shape="mapping")


def get_rate_limit(client, uid):
    """Return the current-only rate limit for one RGW user."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/ratelimit",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW user rate limit", shape="mapping")


def set_rate_limit(
    client,
    uid,
    enabled=False,
    max_read_ops=0,
    max_write_ops=0,
    max_read_bytes=0,
    max_write_bytes=0,
):
    """Set the current-only per-user rate limit."""
    data = {
        "enabled": common.boolean(enabled, "enabled"),
        "max_read_ops": common.non_negative(max_read_ops, "max_read_ops"),
        "max_write_ops": common.non_negative(max_write_ops, "max_write_ops"),
        "max_read_bytes": common.non_negative(max_read_bytes, "max_read_bytes"),
        "max_write_bytes": common.non_negative(max_write_bytes, "max_write_bytes"),
    }
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/{common.segment(uid, 'uid')}/ratelimit",
        api_version=API_VERSION,
        data=data,
    )
    return common.safe_response(response, "RGW user rate limit update")
