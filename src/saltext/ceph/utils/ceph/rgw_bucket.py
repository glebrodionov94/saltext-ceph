"""Public Ceph Dashboard RGW bucket controller operations."""

import json
from collections.abc import Mapping

from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
LIST_API_VERSION = "1.1"
RESOURCE_PATH = "/api/rgw/bucket"
_LOCK_MODES = frozenset(("GOVERNANCE", "COMPLIANCE"))
_ENCRYPTION_TYPES = frozenset(("kms", "s3"))
_KMS_PROVIDERS = frozenset(("vault", "kmip"))
_VAULT_FIELDS = frozenset(
    (
        "addr",
        "auth",
        "prefix",
        "secret_engine",
        "namespace",
        "token_file",
        "ssl_cacert",
        "ssl_clientcert",
        "ssl_clientkey",
        "verify_ssl",
        "backend",
        "encryption_type",
        "unique_id",
    )
)
_KMIP_FIELDS = frozenset(
    (
        "addr",
        "username",
        "password",
        "client_cert",
        "client_key",
        "ca_path",
        "kms_key_template",
        "s3_key_template",
        "backend",
        "encryption_type",
        "unique_id",
    )
)
_REEF_ENCRYPTION_FIELDS = frozenset(
    (
        "auth_method",
        "secret_engine",
        "secret_path",
        "namespace",
        "address",
        "token",
        "owner",
        "ssl_cert",
        "client_cert",
        "client_key",
    )
)


def _optional_bool(value, label):
    return None if value is None else common.boolean(value, label)


def _optional_non_negative(value, label):
    return None if value is None else common.non_negative(value, label)


def _choice(value, label, choices, *, optional=True):
    if value is None and optional:
        return None
    value = common.name(value, label)
    if value not in choices:
        raise ConfigurationError(f"{label} contains an unsupported value.")
    return value


def _json_text(value, label):
    return common.optional_text(value, label, max_length=1024 * 1024)


def _daemon(value):
    return common.optional_text(value, "daemon_name")


def _owner(value):
    return common.optional_text(value, "owner")


def _current_encryption_config(config, kms_provider):
    allowed = _VAULT_FIELDS if kms_provider == "vault" else _KMIP_FIELDS
    required = {"addr", "auth", "prefix", "secret_engine"} if kms_provider == "vault" else {"addr"}
    if set(config) - allowed or not required.issubset(config):
        raise ConfigurationError("config does not match the selected current KMS provider.")
    result = {}
    for field, value in config.items():
        if field == "verify_ssl":
            result[field] = common.boolean(value, f"config {field}")
        elif field in required:
            result[field] = common.text(value, f"config {field}")
        else:
            result[field] = common.optional_text(value, f"config {field}")
    return result


def _reef_encryption_config(config):
    if set(config) - _REEF_ENCRYPTION_FIELDS:
        raise ConfigurationError("config contains fields unsupported by Reef encryption API.")
    return {
        field: common.optional_text(value, f"config {field}")
        for field, value in config.items()
        if value is not None
    }


def _list_response(response, stats):
    if not isinstance(response.data, list):
        raise ProtocolError("RGW bucket list returned an unexpected response shape.")
    if stats:
        if not all(isinstance(item, Mapping) for item in response.data):
            raise ProtocolError("RGW bucket list returned an unexpected response shape.")
    elif not all(isinstance(item, str) for item in response.data):
        raise ProtocolError("RGW bucket list returned an unexpected response shape.")
    return common.safe_response(response, "RGW bucket list")


def list_buckets(client, stats=False, daemon_name=None, uid=None):
    """List RGW buckets through the controller's version 1.1 method."""
    stats = common.boolean(stats, "stats")
    request_params = common.params(
        stats=stats,
        daemon_name=_daemon(daemon_name),
        uid=common.optional_text(uid, "uid"),
    )
    response = client.request(
        "GET", RESOURCE_PATH, api_version=LIST_API_VERSION, params=request_params
    )
    return _list_response(response, stats)


def get_bucket(client, bucket, daemon_name=None):
    """Return one bucket including controller-enriched configuration."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/{common.segment(bucket, 'bucket')}",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name)),
    )
    return common.safe_response(response, "RGW bucket", shape="mapping")


def create_bucket(
    client,
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
):
    """Create a bucket; ``replication`` is sent only when explicitly supplied."""
    lock_enabled = common.boolean(lock_enabled, "lock_enabled")
    encryption_state = common.boolean(encryption_state, "encryption_state")
    replication = _optional_bool(replication, "replication")
    lock_mode = _choice(lock_mode, "lock_mode", _LOCK_MODES)
    if lock_enabled and lock_mode is None:
        raise ConfigurationError("lock_mode is required when lock_enabled=True.")
    encryption_type = _choice(encryption_type, "encryption_type", _ENCRYPTION_TYPES)
    if encryption_state and encryption_type is None:
        raise ConfigurationError("encryption_type is required when encryption_state=True.")
    retention_days = _optional_non_negative(
        lock_retention_period_days, "lock_retention_period_days"
    )
    retention_years = _optional_non_negative(
        lock_retention_period_years, "lock_retention_period_years"
    )
    if retention_days is not None and retention_years is not None:
        raise ConfigurationError("choose only one lock retention period unit.")
    data = common.params(
        bucket=common.name(bucket, "bucket"),
        uid=common.name(uid, "uid"),
        zonegroup=common.optional_text(zonegroup, "zonegroup"),
        placement_target=common.optional_text(placement_target, "placement_target"),
        lock_enabled=lock_enabled,
        lock_mode=lock_mode,
        lock_retention_period_days=retention_days,
        lock_retention_period_years=retention_years,
        encryption_state=encryption_state,
        encryption_type=encryption_type,
        key_id=common.optional_text(key_id, "key_id"),
        tags=_json_text(tags, "tags"),
        bucket_policy=_json_text(bucket_policy, "bucket_policy"),
        canned_acl=common.optional_text(canned_acl, "canned_acl"),
        replication=replication,
        daemon_name=_daemon(daemon_name),
    )
    response = client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)
    return common.safe_response(response, "RGW bucket creation")


def update_bucket(
    client,
    bucket,
    bucket_id,
    uid=None,
    versioning_state=None,
    encryption_state=None,
    encryption_type=None,
    key_id=None,
    mfa_delete=None,
    mfa_token_serial=None,
    mfa_token_pin=None,
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
):
    """Update bucket ownership and features across Reef and current Ceph."""
    lifecycle_requested = lifecycle is not None
    encryption_requested = encryption_state is not None
    if encryption_requested:
        encryption_state = common.boolean(encryption_state, "encryption_state")
        if not encryption_state:
            common.confirm(confirm_encryption_disable)
    if encryption_state is None or lifecycle is None or uid is None:
        current = get_bucket(client, bucket, daemon_name).data
        if uid is None:
            owner = current.get("owner")
            if not isinstance(owner, str) or not owner:
                raise ProtocolError("RGW bucket response cannot safely determine its owner.")
            uid = owner
        if encryption_state is None:
            status = current.get("encryption")
            if status not in ("Enabled", "Disabled"):
                raise ProtocolError("RGW bucket response cannot safely preserve encryption state.")
            encryption_state = status == "Enabled"
        if lifecycle is None and "lifecycle" in current:
            lifecycle = current["lifecycle"]
            if isinstance(lifecycle, Mapping):
                lifecycle = json.dumps(lifecycle, separators=(",", ":"), sort_keys=True)
            elif lifecycle is not None and not isinstance(lifecycle, str):
                raise ProtocolError("RGW bucket response cannot safely preserve lifecycle policy.")
        elif lifecycle is None and "replication" in current:
            raise ProtocolError("RGW bucket response omitted its current lifecycle policy.")
    encryption_state = common.boolean(encryption_state, "encryption_state")
    if lifecycle_requested and isinstance(lifecycle, str) and lifecycle.strip() == "{}":
        common.confirm(confirm_lifecycle_delete)
    replication = _optional_bool(replication, "replication")
    common.boolean(confirm_replication_disable, "confirm_replication_disable")
    if replication is False:
        common.confirm(confirm_replication_disable)
    versioning_state = _choice(
        versioning_state, "versioning_state", frozenset(("Enabled", "Suspended"))
    )
    lock_mode = _choice(lock_mode, "lock_mode", _LOCK_MODES)
    encryption_type = _choice(encryption_type, "encryption_type", _ENCRYPTION_TYPES)
    retention_days = _optional_non_negative(
        lock_retention_period_days, "lock_retention_period_days"
    )
    retention_years = _optional_non_negative(
        lock_retention_period_years, "lock_retention_period_years"
    )
    if retention_days is not None and retention_years is not None:
        raise ConfigurationError("choose only one lock retention period unit.")
    data = common.params(
        bucket_id=common.name(bucket_id, "bucket_id"),
        uid=common.optional_text(uid, "uid"),
        versioning_state=versioning_state,
        encryption_state=encryption_state,
        encryption_type=encryption_type,
        key_id=common.optional_text(key_id, "key_id"),
        mfa_delete=common.optional_text(mfa_delete, "mfa_delete"),
        mfa_token_serial=common.optional_text(mfa_token_serial, "mfa_token_serial"),
        mfa_token_pin=common.optional_text(mfa_token_pin, "mfa_token_pin"),
        lock_mode=lock_mode,
        lock_retention_period_days=retention_days,
        lock_retention_period_years=retention_years,
        tags=_json_text(tags, "tags"),
        bucket_policy=_json_text(bucket_policy, "bucket_policy"),
        canned_acl=common.optional_text(canned_acl, "canned_acl"),
        replication=replication,
        lifecycle=_json_text(lifecycle, "lifecycle"),
        daemon_name=_daemon(daemon_name),
    )
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/{common.segment(bucket, 'bucket')}",
        api_version=API_VERSION,
        data=data,
    )
    return common.safe_response(response, "RGW bucket update")


def delete_bucket(client, bucket, daemon_name=None, confirm=False):
    """Delete an empty RGW bucket after explicit confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{common.segment(bucket, 'bucket')}",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name)),
    )
    return common.safe_response(response, "RGW bucket deletion")


def set_encryption_config(
    client,
    encryption_type,
    kms_provider,
    config,
    daemon_name,
    reef_legacy=False,
):
    """Set current structured KMS config or Reef's flattened legacy config."""
    encryption_type = _choice(encryption_type, "encryption_type", _ENCRYPTION_TYPES, optional=False)
    kms_provider = _choice(kms_provider, "kms_provider", _KMS_PROVIDERS, optional=False)
    config = common.mapping(config, "config")
    reef_legacy = common.boolean(reef_legacy, "reef_legacy")
    daemon_name = common.name(daemon_name, "daemon_name")
    if reef_legacy:
        data = {
            "encryption_type": encryption_type,
            "kms_provider": kms_provider,
            **_reef_encryption_config(config),
        }
        data["daemon_name"] = daemon_name
    else:
        data = {
            "encryption_type": encryption_type,
            "kms_provider": kms_provider,
            "config": _current_encryption_config(config, kms_provider),
            "daemon_name": daemon_name,
        }
    response = client.request(
        "PUT", f"{RESOURCE_PATH}/setEncryptionConfig", api_version=API_VERSION, data=data
    )
    return common.safe_response(response, "RGW encryption configuration")


def get_encryption(client, bucket_name, daemon_name=None, owner=None):
    """Read server-side encryption state for a bucket."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/getEncryption",
        api_version=API_VERSION,
        params=common.params(
            bucket_name=common.name(bucket_name, "bucket_name"),
            daemon_name=_daemon(daemon_name),
            owner=_owner(owner),
        ),
    )
    return common.safe_response(response, "RGW bucket encryption", shape="mapping")


def delete_encryption(client, bucket_name, daemon_name=None, owner=None, confirm=False):
    """Remove bucket encryption after explicit confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/deleteEncryption",
        api_version=API_VERSION,
        params=common.params(
            bucket_name=common.name(bucket_name, "bucket_name"),
            daemon_name=_daemon(daemon_name),
            owner=_owner(owner),
        ),
    )
    return common.safe_response(response, "RGW bucket encryption deletion")


def get_encryption_config(client, daemon_name=None, owner=None, include_secrets=False):
    """Read encryption configuration, redacting key material by default."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/getEncryptionConfig",
        api_version=API_VERSION,
        params=common.params(daemon_name=_daemon(daemon_name), owner=_owner(owner)),
    )
    return common.safe_response(
        response, "RGW encryption configuration", include_secrets=include_secrets
    )


def set_lifecycle(
    client,
    bucket_name,
    lifecycle,
    daemon_name=None,
    owner=None,
    tenant=None,
    confirm_delete=False,
):
    """Set the current-only bucket lifecycle policy; ``'{}'`` deletes it in Ceph."""
    lifecycle = _json_text(lifecycle, "lifecycle")
    if lifecycle is None:
        raise ConfigurationError("lifecycle must be bounded text.")
    if lifecycle.strip() == "{}":
        common.confirm(confirm_delete)
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/lifecycle",
        api_version=API_VERSION,
        data=common.params(
            bucket_name=common.name(bucket_name, "bucket_name"),
            lifecycle=lifecycle,
            daemon_name=_daemon(daemon_name),
            owner=_owner(owner),
            tenant=common.optional_text(tenant, "tenant"),
        ),
    )
    return common.safe_response(response, "RGW bucket lifecycle update")


def get_lifecycle(client, bucket_name, daemon_name=None, owner=None, tenant=None):
    """Read the current-only bucket lifecycle policy."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/lifecycle",
        api_version=API_VERSION,
        params=common.params(
            bucket_name=common.name(bucket_name, "bucket_name"),
            daemon_name=_daemon(daemon_name),
            owner=_owner(owner),
            tenant=common.optional_text(tenant, "tenant"),
        ),
    )
    return common.safe_response(response, "RGW bucket lifecycle")


def get_notifications(client, bucket_name, daemon_name=None, owner=None):
    """Read current-only S3 bucket notifications."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/notification",
        api_version=API_VERSION,
        params=common.params(
            bucket_name=common.name(bucket_name, "bucket_name"),
            daemon_name=_daemon(daemon_name),
            owner=_owner(owner),
        ),
    )
    return common.safe_response(response, "RGW bucket notifications")


def set_notifications(
    client,
    bucket_name,
    notification,
    daemon_name=None,
    owner=None,
    confirm_delete=False,
):
    """Create or replace current-only S3 bucket notification XML/JSON text."""
    notification = _json_text(notification, "notification")
    if notification is None:
        raise ConfigurationError("notification must be bounded text.")
    if notification.strip() == "{}":
        common.confirm(confirm_delete)
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/notification",
        api_version=API_VERSION,
        data=common.params(
            bucket_name=common.name(bucket_name, "bucket_name"),
            notification=notification,
            daemon_name=_daemon(daemon_name),
            owner=_owner(owner),
        ),
    )
    return common.safe_response(response, "RGW bucket notification update")


def delete_notification(
    client, bucket_name, notification_id, daemon_name=None, owner=None, confirm=False
):
    """Delete one current-only bucket notification after confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/notification",
        api_version=API_VERSION,
        params=common.params(
            bucket_name=common.name(bucket_name, "bucket_name"),
            notification_id=common.name(notification_id, "notification_id"),
            daemon_name=_daemon(daemon_name),
            owner=_owner(owner),
        ),
    )
    return common.safe_response(response, "RGW bucket notification deletion")


def get_global_rate_limit(client):
    """Return the current-only global RGW bucket rate limit."""
    response = client.request("GET", f"{RESOURCE_PATH}/ratelimit", api_version=API_VERSION)
    return common.safe_response(response, "RGW global bucket rate limit", shape="mapping")


def get_rate_limit(client, bucket_id):
    """Return the current-only rate limit for one bucket identifier."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/{common.segment(bucket_id, 'bucket_id')}/ratelimit",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW bucket rate limit", shape="mapping")


def set_rate_limit(
    client,
    bucket_id,
    enabled,
    max_read_ops,
    max_write_ops,
    max_read_bytes,
    max_write_bytes,
):
    """Set the current-only per-bucket rate limit."""
    data = {
        "enabled": common.boolean(enabled, "enabled"),
        "max_read_ops": common.non_negative(max_read_ops, "max_read_ops"),
        "max_write_ops": common.non_negative(max_write_ops, "max_write_ops"),
        "max_read_bytes": common.non_negative(max_read_bytes, "max_read_bytes"),
        "max_write_bytes": common.non_negative(max_write_bytes, "max_write_bytes"),
    }
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/{common.segment(bucket_id, 'bucket_id')}/ratelimit",
        api_version=API_VERSION,
        data=data,
    )
    return common.safe_response(response, "RGW bucket rate limit update")
