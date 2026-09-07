"""Pure helpers shared by the Ceph event beacons.

The helpers deliberately keep API response bodies out of Salt ``__context__``.
Only bounded status maps and SHA-256 fingerprints are retained between runs.
"""

import hashlib
import heapq
import json
import math
import re
from collections.abc import Mapping
from collections.abc import MutableMapping
from datetime import datetime
from datetime import timezone

CONTEXT_KEY = "saltext.ceph.beacons"
MAX_CONFIG_ENTRIES = 64
MAX_CONTEXT_INSTANCES = 32
MAX_HEALTH_CHECKS = 1024
MAX_CERTIFICATES = 512
MAX_TASK_METADATA_BYTES = 65536

COMMON_CONFIG_KEYS = frozenset(
    {
        "_beacon_name",
        "beacon_module",
        "disable_during_state_run",
        "enabled",
        "interval",
        "profile",
        "run_once",
    }
)


def render_config(config):
    """Return Salt's list-based beacon configuration as a plain dictionary."""
    if not isinstance(config, list):
        raise ValueError("configuration must be a list")
    if len(config) > MAX_CONFIG_ENTRIES:
        raise ValueError(f"configuration must contain at most {MAX_CONFIG_ENTRIES} entries")
    rendered = {}
    for item in config:
        if not isinstance(item, Mapping):
            raise ValueError("configuration entries must be mappings")
        if any(
            not isinstance(key, str)
            or not key
            or len(key) > 128
            or re.search(r"[\x00-\x1f\x7f]", key)
            for key in item
        ):
            raise ValueError("configuration option names must be bounded strings")
        rendered.update(item)
        if len(rendered) > MAX_CONFIG_ENTRIES:
            raise ValueError(f"configuration must contain at most {MAX_CONFIG_ENTRIES} options")
    return rendered


def validate_config(config, allowed_keys):
    """Validate common Salt beacon options and return ``(mapping, error)``."""
    try:
        rendered = render_config(config)
    except ValueError as exc:
        return None, str(exc)

    unknown = sorted(set(rendered).difference(COMMON_CONFIG_KEYS | set(allowed_keys)))
    if unknown:
        displayed = ", ".join(unknown[:8])
        if len(unknown) > 8:
            displayed += f", ... ({len(unknown)} total)"
        return None, f"unsupported option(s): {displayed}"

    profile = rendered.get("profile", "default")
    if (
        not isinstance(profile, str)
        or not profile
        or len(profile) > 128
        or re.search(r"[\x00-\x1f\x7f]", profile)
    ):
        return None, "profile must be a non-empty string no longer than 128 characters"

    if "interval" in rendered:
        interval = rendered["interval"]
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or not math.isfinite(interval)
            or interval <= 0
        ):
            return None, "interval must be a positive finite number of seconds"

    for option in ("disable_during_state_run", "enabled", "run_once"):
        if option in rendered and not isinstance(rendered[option], bool):
            return None, f"{option} must be a boolean"

    for option in ("beacon_module", "_beacon_name"):
        if option in rendered and (
            not isinstance(rendered[option], str)
            or not rendered[option]
            or len(rendered[option]) > 128
            or re.search(r"[\x00-\x1f\x7f]", rendered[option])
        ):
            return None, f"{option} must be a non-empty string"
    return rendered, None


def response_data(response):
    """Unwrap an APIResponse, its Salt envelope, or an already-unwrapped body."""
    if hasattr(response, "data") and hasattr(response, "status"):
        status, data = response.status, response.data
    elif isinstance(response, Mapping) and "status" in response and "data" in response:
        status, data = response["status"], response["data"]
    else:
        return response
    if isinstance(status, bool) or not isinstance(status, int) or not 200 <= status < 300:
        raise ValueError("API response has an unsuccessful or invalid status")
    return data


def fingerprint(value, max_bytes=None):
    """Return a deterministic fingerprint for a bounded JSON-compatible value."""
    if max_bytes is not None and (
        isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0
    ):
        raise ValueError("max_bytes must be a positive integer")
    digest = hashlib.sha256()
    try:
        encoder = json.JSONEncoder(
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        size = 0
        for chunk in encoder.iterencode(value):
            encoded = chunk.encode("ascii")
            size += len(encoded)
            if max_bytes is not None and size > max_bytes:
                raise ValueError("value exceeds the fingerprint size limit")
            digest.update(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("value is not JSON-compatible") from exc
    return digest.hexdigest()


def instance_id(config):
    """Identify a named beacon configuration without retaining its contents."""
    ignored = {"disable_during_state_run", "enabled", "interval", "run_once"}
    identity = {key: value for key, value in config.items() if key not in ignored}
    return fingerprint(identity)[:24]


def context_state(context, beacon_name, identity):
    """Return an isolated, bounded state mapping from Salt ``__context__``.

    Invalid or unavailable loader context produces an ephemeral mapping. Existing
    values outside this extension's single namespace are never inspected.
    """
    if not isinstance(context, MutableMapping):
        return {}
    root = context.get(CONTEXT_KEY)
    if not isinstance(root, dict):
        root = {}
        context[CONTEXT_KEY] = root
    bucket = root.get(beacon_name)
    if not isinstance(bucket, dict):
        bucket = {}
        root[beacon_name] = bucket
    state = bucket.get(identity)
    if not isinstance(state, dict):
        while len(bucket) >= MAX_CONTEXT_INSTANCES:
            bucket.pop(next(iter(bucket)))
        state = {}
        bucket[identity] = state
    return state


def health_observation(data, max_checks):
    """Return a bounded, secret-free health observation and its fingerprint."""
    if not isinstance(data, Mapping) or not isinstance(data.get("health"), Mapping):
        raise ValueError("health response has an unexpected shape")
    health = data["health"]
    status = health.get("status")
    if not isinstance(status, str) or not status or len(status) > 64:
        raise ValueError("health response has no valid status")

    raw_checks = health.get("checks", [])
    if isinstance(raw_checks, Mapping):
        reported_check_count = len(raw_checks)
        check_items = heapq.nsmallest(
            MAX_HEALTH_CHECKS,
            raw_checks.items(),
            key=lambda item: str(item[0]),
        )
    elif isinstance(raw_checks, list):
        reported_check_count = len(raw_checks)
        check_items = [
            (None, raw_checks[index]) for index in range(min(len(raw_checks), MAX_HEALTH_CHECKS))
        ]
    else:
        raise ValueError("health checks have an unexpected shape")

    checks = []
    for supplied_name, item in check_items:
        if not isinstance(item, Mapping):
            raise ValueError("health check has an unexpected shape")
        name = item.get("type", supplied_name)
        if not isinstance(name, str) or not name:
            name = "unknown"
        record = {"name": name[:128]}
        severity = item.get("severity")
        if isinstance(severity, str) and severity:
            record["severity"] = severity[:64]
        summary = item.get("summary")
        count = None
        if isinstance(summary, Mapping):
            message = summary.get("message")
            count = summary.get("count")
        else:
            message = summary
        if isinstance(message, str) and message:
            record["message"] = message[:512]
        if isinstance(count, int) and not isinstance(count, bool):
            record["count"] = count
        if isinstance(item.get("muted"), bool):
            record["muted"] = item["muted"]
        checks.append(record)
    checks.sort(key=lambda item: (item["name"], item.get("severity", "")))
    digest = fingerprint(
        {"status": status, "reported_check_count": reported_check_count, "checks": checks}
    )
    return {
        "status": status,
        "fingerprint": digest,
        "check_count": reported_check_count,
        "checks": checks[:max_checks],
    }


def task_identity(task):
    """Return a stable private identity for one finished Dashboard task."""
    if not isinstance(task, Mapping):
        raise ValueError("task must be a mapping")
    name = task.get("name")
    success = task.get("success")
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 255
        or re.search(r"[\x00-\x1f\x7f]", name)
        or not isinstance(success, bool)
    ):
        raise ValueError("task has no valid name or success status")
    metadata = task.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("task has no valid metadata")
    timestamps = {}
    for field in ("begin_time", "end_time"):
        value = task.get(field)
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 128
            or re.search(r"[\x00-\x1f\x7f]", value)
        ):
            raise ValueError(f"task has no valid {field}")
        timestamps[field] = value
    duration = task.get("duration")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration < 0
    ):
        raise ValueError("task has no valid duration")
    identity = {
        "name": name,
        "metadata_fingerprint": fingerprint(metadata, max_bytes=MAX_TASK_METADATA_BYTES),
        **timestamps,
        "duration": duration,
        "success": success,
    }
    return fingerprint(identity)


def task_event(task):
    """Build a bounded event without task metadata, return values, or exceptions."""
    public_id = fingerprint(
        {
            "name": task["name"],
            "begin_time": task.get("begin_time"),
            "end_time": task.get("end_time"),
            "success": task["success"],
        }
    )
    event = {
        "task_id": public_id,
        "name": task["name"][:255],
        "success": task["success"],
    }
    for field in ("begin_time", "end_time"):
        value = task.get(field)
        if isinstance(value, str):
            event[field] = value[:128]
    for field in ("duration", "progress"):
        value = task.get(field)
        if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value):
            event[field] = value
    return event


def utcnow():
    """Return the current aware UTC time; kept separate for deterministic tests."""
    return datetime.now(timezone.utc)


def days_until(value, now=None):
    """Return whole days until an ISO-8601 timestamp, or ``None`` if invalid."""
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        expiry = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    else:
        expiry = expiry.astimezone(timezone.utc)
    current = utcnow() if now is None else now
    if not isinstance(current, datetime):
        raise ValueError("now must be a datetime")
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return math.floor((expiry - current).total_seconds() / 86400)


def certificate_observation(entry, warning_days, critical_days, now):
    """Classify one certificate and return its identity, level, and safe fields."""
    if not isinstance(entry, Mapping):
        raise ValueError("certificate must be a mapping")
    cert_name = entry.get("cert_name")
    if (
        not isinstance(cert_name, str)
        or not cert_name
        or len(cert_name) > 255
        or re.search(r"[\x00-\x1f\x7f]", cert_name)
    ):
        raise ValueError("certificate has no valid name")
    scope = entry.get("scope") if isinstance(entry.get("scope"), str) else ""
    target = entry.get("target") if isinstance(entry.get("target"), str) else ""
    if len(scope) > 64 or re.search(r"[\x00-\x1f\x7f]", scope):
        scope = ""
    if len(target) > 255 or re.search(r"[\x00-\x1f\x7f]", target):
        target = ""
    cert_id = fingerprint({"cert_name": cert_name, "scope": scope, "target": target})

    expiry_date = entry.get("expiry_date")
    if isinstance(expiry_date, str) and (
        len(expiry_date) > 128 or re.search(r"[\x00-\x1f\x7f]", expiry_date)
    ):
        expiry_date = None
    days = days_until(expiry_date, now=now)
    api_days = entry.get("days_to_expiration")
    if days is None and isinstance(api_days, int) and not isinstance(api_days, bool):
        days = api_days

    status = entry.get("status")
    if (
        not isinstance(status, str)
        or not status
        or len(status) > 64
        or re.search(r"[\x00-\x1f\x7f]", status)
    ):
        status = "unknown"
    else:
        status = status.lower()
    if status == "expired" or (days is not None and days < 0):
        level = "expired"
    elif status not in ("valid", "expiring", "expired"):
        level = "critical"
    elif days is not None and days <= critical_days:
        level = "critical"
    elif status == "expiring" or (days is not None and days <= warning_days):
        level = "warning"
    else:
        level = "healthy"

    observation = {
        "certificate_id": cert_id,
        "cert_name": cert_name[:255],
        "scope": scope[:64],
        "target": target[:255],
        "status": status[:64],
        "days_to_expiration": days,
    }
    if isinstance(expiry_date, str):
        observation["expiry_date"] = expiry_date[:128]
    return cert_id, level, observation


def bounded_certificates(entries):
    """Return certificates in stable order, capped before event processing."""
    if not isinstance(entries, list) or not all(isinstance(item, Mapping) for item in entries):
        raise ValueError("certificate response has an unexpected shape")
    candidates = (
        item
        for item in entries
        if isinstance(item.get("cert_name"), str)
        and item["cert_name"]
        and len(item["cert_name"]) <= 255
        and not re.search(r"[\x00-\x1f\x7f]", item["cert_name"])
    )
    return heapq.nsmallest(
        MAX_CERTIFICATES,
        candidates,
        key=lambda item: (
            item["cert_name"],
            str(item.get("scope", ""))[:64],
            str(item.get("target", ""))[:255],
        ),
    )
