"""Public RGW role APIs and current-only account APIs."""

import json
import math
import re
from collections.abc import Mapping

from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
REEF_ROLE_PATH = "/api/rgw/roles"
ACCOUNT_PATH = "/api/rgw/accounts"
_ROLE_NAME = re.compile(r"[0-9A-Za-z_+=,.@-]{1,64}")
_ACCOUNT_ID = re.compile(r"RGW[0-9]{17}")


def _daemon(value):
    return common.optional_text(value, "daemon_name")


def _account_id(value):
    value = common.name(value, "account_id")
    if not _ACCOUNT_ID.fullmatch(value):
        raise ConfigurationError("account_id must be RGW followed by 17 decimal digits.")
    return value


def _role_name(value):
    if not isinstance(value, str) or not _ROLE_NAME.fullmatch(value):
        raise ConfigurationError("role_name contains unsupported characters or is too long.")
    return value


def _role_path(value):
    value = common.text(value, "role_path", max_length=512)
    if not value.startswith("/") or not value.endswith("/"):
        raise ConfigurationError("role_path must start and end with '/'.")
    return value


def _policy_document(value):
    value = common.optional_text(value, "role_assume_policy_doc", max_length=1024 * 1024)
    if not value:
        return value
    try:
        document = json.loads(value)
    except ValueError:
        raise ConfigurationError("role_assume_policy_doc must be valid JSON.") from None
    if not isinstance(document, dict):
        raise ConfigurationError("role_assume_policy_doc must contain a JSON object.")
    return value


def _account_role_path(account_id):
    if account_id is None:
        return REEF_ROLE_PATH
    return f"{ACCOUNT_PATH}/{common.segment(_account_id(account_id), 'account_id')}/roles"


def list_roles(client, account_id=None):
    """List Reef global roles or current account-scoped roles."""
    response = client.request("GET", _account_role_path(account_id), api_version=API_VERSION)
    return common.safe_response(response, "RGW role list", shape="mapping_list")


def get_role(client, account_id, role_name):
    """Return one role through the current-only account-scoped route."""
    path = _account_role_path(account_id)
    response = client.request(
        "GET",
        f"{path}/{common.segment(_role_name(role_name), 'role_name')}",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW role", shape="mapping")


def create_role(client, role_name, role_path, role_assume_policy_doc="", account_id=None):
    """Create a Reef global role or a current account-scoped role."""
    response = client.request(
        "POST",
        _account_role_path(account_id),
        api_version=API_VERSION,
        data={
            "role_name": _role_name(role_name),
            "role_path": _role_path(role_path),
            "role_assume_policy_doc": _policy_document(role_assume_policy_doc),
        },
    )
    return common.safe_response(response, "RGW role creation")


def update_role(client, role_name, max_session_duration, account_id=None):
    """Update a Reef global role or current account-scoped role."""
    try:
        duration = float(max_session_duration)
    except (TypeError, ValueError):
        raise ConfigurationError("max_session_duration must be between 1 and 12 hours.") from None
    if not math.isfinite(duration) or not 1 <= duration <= 12:
        raise ConfigurationError("max_session_duration must be between 1 and 12 hours.")
    response = client.request(
        "PUT",
        _account_role_path(account_id),
        api_version=API_VERSION,
        data={
            "role_name": _role_name(role_name),
            "max_session_duration": str(max_session_duration),
        },
    )
    return common.safe_response(response, "RGW role update")


def delete_role(client, role_name, account_id=None, confirm=False):
    """Delete a Reef global or current account-scoped role after confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{_account_role_path(account_id)}/{common.segment(_role_name(role_name), 'role_name')}",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW role deletion")


def _limits(values):
    result = {}
    for key, value in values.items():
        if value is not None:
            result[key] = common.non_negative(value, key)
    return result


def create_account(
    client,
    account_name,
    tenant=None,
    email=None,
    max_buckets=None,
    max_users=None,
    max_roles=None,
    max_groups=None,
    max_access_keys=None,
    daemon_name=None,
):
    """Create an RGW account through the current-only account controller."""
    data = common.params(
        account_name=common.name(account_name, "account_name"),
        tenant=common.optional_text(tenant, "tenant"),
        email=common.optional_text(email, "email"),
        daemon_name=_daemon(daemon_name),
        **_limits(
            {
                "max_buckets": max_buckets,
                "max_users": max_users,
                "max_roles": max_roles,
                "max_group": max_groups,
                "max_access_keys": max_access_keys,
            }
        ),
    )
    response = client.request("POST", ACCOUNT_PATH, api_version=API_VERSION, data=data)
    return common.safe_response(response, "RGW account creation", shape="mapping")


def list_accounts(client, daemon_name=None, detailed=False):
    """List current-only account IDs or detailed account mappings."""
    detailed = common.boolean(detailed, "detailed")
    response = client.request(
        "GET",
        ACCOUNT_PATH,
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name), detailed=True if detailed else None),
    )
    if not isinstance(response.data, list):
        raise ProtocolError("RGW account list returned an unexpected response shape.")
    expected = Mapping if detailed else str
    if not all(isinstance(item, expected) for item in response.data):
        raise ProtocolError("RGW account list returned an unexpected response shape.")
    return common.safe_response(response, "RGW account list")


def get_account(client, account_id, daemon_name=None):
    """Return one current-only RGW account."""
    response = client.request(
        "GET",
        f"{ACCOUNT_PATH}/{common.segment(_account_id(account_id), 'account_id')}",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name)),
    )
    return common.safe_response(response, "RGW account", shape="mapping")


def account_exists(client, account_name, daemon_name=None):
    """Check whether a current-only RGW account name exists."""
    response = client.request(
        "GET",
        f"{ACCOUNT_PATH}/exists",
        api_version=API_VERSION,
        params=common.params(
            account_name=common.name(account_name, "account_name"),
            daemon_name=_daemon(daemon_name),
        ),
    )
    return common.safe_response(response, "RGW account existence", shape="boolean")


def update_account(
    client,
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
):
    """Update a current-only RGW account."""
    data = common.params(
        account_name=common.name(account_name, "account_name"),
        email=common.optional_text(email, "email"),
        tenant=common.optional_text(tenant, "tenant"),
        daemon_name=_daemon(daemon_name),
        **_limits(
            {
                "max_buckets": max_buckets,
                "max_users": max_users,
                "max_roles": max_roles,
                "max_group": max_groups,
                "max_access_keys": max_access_keys,
            }
        ),
    )
    response = client.request(
        "PUT",
        f"{ACCOUNT_PATH}/{common.segment(_account_id(account_id), 'account_id')}",
        api_version=API_VERSION,
        data=data,
    )
    return common.safe_response(response, "RGW account update", shape="mapping")


def delete_account(client, account_id, daemon_name=None, confirm=False):
    """Delete a current-only RGW account after explicit confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{ACCOUNT_PATH}/{common.segment(_account_id(account_id), 'account_id')}",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name)),
    )
    return common.safe_response(response, "RGW account deletion")


def set_account_quota(client, account_id, quota_type, max_size, max_objects, enabled):
    """Set a current-only account or bucket quota for an account."""
    quota_type = common.name(quota_type, "quota_type")
    if quota_type not in ("account", "bucket"):
        raise ConfigurationError("quota_type must be account or bucket.")
    response = client.request(
        "PUT",
        f"{ACCOUNT_PATH}/{common.segment(_account_id(account_id), 'account_id')}/quota",
        api_version=API_VERSION,
        data={
            "quota_type": quota_type,
            "max_size": common.text(max_size, "max_size", max_length=128),
            "max_objects": common.text(max_objects, "max_objects", max_length=128),
            "enabled": common.boolean(enabled, "enabled"),
        },
    )
    return common.safe_response(response, "RGW account quota update")


def set_account_quota_status(client, account_id, quota_type, quota_status):
    """Enable or disable a current-only account or bucket quota."""
    quota_type = common.name(quota_type, "quota_type")
    quota_status = common.name(quota_status, "quota_status")
    if quota_type not in ("account", "bucket"):
        raise ConfigurationError("quota_type must be account or bucket.")
    if quota_status not in ("enable", "disable"):
        raise ConfigurationError("quota_status must be enable or disable.")
    response = client.request(
        "PUT",
        f"{ACCOUNT_PATH}/{common.segment(_account_id(account_id), 'account_id')}/quota/status",
        api_version=API_VERSION,
        data={"quota_type": quota_type, "quota_status": quota_status},
    )
    return common.safe_response(response, "RGW account quota status update")
