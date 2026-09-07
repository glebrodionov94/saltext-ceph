"""Pure normalization helpers for declarative RGW state modules."""

import json
from collections.abc import Mapping
from collections.abc import Sequence

from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

RATE_FIELDS = (
    "enabled",
    "max_read_ops",
    "max_write_ops",
    "max_read_bytes",
    "max_write_bytes",
)

_VERSIONING_STATUSES = {
    "enabled": "Enabled",
    "suspended": "Suspended",
    "off": "Off",
}


def mapping(value, label):
    """Return a detached response mapping or raise a protocol error."""
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    return dict(value)


def list_of_mappings(value, label):
    """Return detached response mappings with strict shape validation."""
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    return [dict(item) for item in value]


def find_unique(values, wanted, keys, label):
    """Find one mapping by any of the declared identity keys."""
    values = list_of_mappings(values, label)
    matches = [item for item in values if any(item.get(key) == wanted for key in keys)]
    if len(matches) > 1:
        raise ProtocolError(f"{label} returned duplicate resources for {wanted}.")
    return matches[0] if matches else None


def json_value(value, label, *, mapping_only=False, non_empty=False):
    """Normalize a JSON string or native JSON value for semantic comparison."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            raise ConfigurationError(f"{label} must contain valid JSON.") from None
    value = common.json_value(value, label)
    if mapping_only and not isinstance(value, dict):
        raise ConfigurationError(f"{label} must contain a JSON object.")
    if non_empty and not value:
        raise ConfigurationError(f"{label} must not be empty.")
    return value


def json_text(value, label, *, mapping_only=False, non_empty=False):
    """Return canonical compact JSON text after semantic validation."""
    value = json_value(value, label, mapping_only=mapping_only, non_empty=non_empty)
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonical(value):
    """Return a recursively deterministic representation for comparisons."""
    if isinstance(value, Mapping):
        return {key: canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [canonical(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    return value


def names(value, label):
    """Validate and sort a duplicate-free sequence of RGW names."""
    return sorted(common.string_list(value, label))


def bool_or_none(value, label):
    """Validate an optional strict boolean."""
    return None if value is None else common.boolean(value, label)


def response_bool(value, label):
    """Normalize booleans emitted by Admin Ops as bools or lowercase text."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.casefold() in ("true", "false"):
        return value.casefold() == "true"
    raise ProtocolError(f"RGW response field {label} is not a boolean.")


def versioning_status(value):
    """Normalize versioning status returned by supported Dashboard releases.

    Reef reports a bucket that has never enabled versioning as ``Suspended``.
    Newer Dashboard releases preserve that distinct state as ``Off``.  Both are
    readable current states, while writes remain limited to the S3 values
    ``Enabled`` and ``Suspended``.
    """
    if isinstance(value, Mapping):
        value = value.get("Status", value.get("status"))
    if isinstance(value, str):
        normalized = _VERSIONING_STATUSES.get(value.strip().casefold())
        if normalized is not None:
            return normalized
    raise ProtocolError("RGW bucket read omitted a usable versioning status.")


def integer_or_none(value, label, *, non_negative=False):
    """Validate an optional integer."""
    if value is None:
        return None
    return common.non_negative(value, label) if non_negative else common.integer(value, label)


def rate_desired(enabled, max_read_ops, max_write_ops, max_read_bytes, max_write_bytes):
    """Normalize the complete writable rate-limit projection."""
    return {
        "enabled": common.boolean(enabled, "enabled"),
        "max_read_ops": common.non_negative(max_read_ops, "max_read_ops"),
        "max_write_ops": common.non_negative(max_write_ops, "max_write_ops"),
        "max_read_bytes": common.non_negative(max_read_bytes, "max_read_bytes"),
        "max_write_bytes": common.non_negative(max_write_bytes, "max_write_bytes"),
    }


def rate_view(value, scope):
    """Read a per-resource rate limit from direct or radosgw-admin output."""
    value = mapping(value, "RGW rate limit")
    nested = value.get(f"{scope}_ratelimit", value)
    nested = mapping(nested, "RGW rate limit")
    if not all(field in nested for field in RATE_FIELDS):
        raise ProtocolError("RGW rate limit omitted a managed field.")
    result = {field: nested[field] for field in RATE_FIELDS}
    for field in RATE_FIELDS[1:]:
        result[field] = common.non_negative(result[field], field)
    result["enabled"] = response_bool(result["enabled"], "enabled")
    return result


def policy_arns(value):
    """Normalize current Ceph managed-policy list response variants."""
    if isinstance(value, Mapping):
        for key in ("Policies", "policies", "AttachedPolicies", "attached_policies"):
            if key in value:
                value = value[key]
                break
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ProtocolError("RGW managed policy list returned an unexpected response shape.")
    result = []
    for item in value:
        if isinstance(item, str):
            arn = item
        elif isinstance(item, Mapping):
            arn = next(
                (
                    item[key]
                    for key in ("PolicyArn", "policy_arn", "arn")
                    if isinstance(item.get(key), str)
                ),
                None,
            )
        else:
            arn = None
        if not arn:
            raise ProtocolError("RGW managed policy list returned an unexpected response shape.")
        result.append(common.name(arn, "policy ARN"))
    if len(result) != len(set(result)):
        raise ProtocolError("RGW managed policy list returned duplicate policy ARNs.")
    return sorted(result)


def validate_secret_sources(*sources):
    """Validate secret files without retaining or returning their contents."""
    for source in sources:
        if source is not None:
            common.secret_from_file(source, "secret")
