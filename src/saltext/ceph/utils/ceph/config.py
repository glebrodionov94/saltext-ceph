"""Validated connection settings, independent of Salt loader globals."""

import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from urllib.parse import unquote
from urllib.parse import urlsplit

from saltext.ceph.utils.ceph.errors import ConfigurationError


def validate_path(path):
    """Reject ambiguous paths before attaching credentials to a request."""
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise ConfigurationError("Expected an absolute URL path, without a host.")
    if "//" in path or re.search(r"[\x00-\x20\x7f\\?#]", path):
        raise ConfigurationError("URL path contains unsupported or ambiguous characters.")
    if re.search(r"%(?![0-9A-Fa-f]{2})", path):
        raise ConfigurationError("URL path contains unsupported or ambiguous characters.")
    decoded = unquote(path)
    if (
        re.search(r"[\x00-\x1f\x7f\\]", decoded)
        or "%" in decoded
        or any(part in (".", "..") for part in decoded.split("/"))
    ):
        raise ConfigurationError("URL path contains unsupported or ambiguous characters.")


@dataclass(frozen=True, repr=False)
class ConnectionConfig:
    """One Dashboard connection; secret-bearing settings have no generated repr.

    ``url`` is the Dashboard root, optionally including its reverse-proxy prefix,
    without ``/api``. Use either ``token`` or ``username`` and ``password``.
    Timeouts are positive seconds. ``verify`` accepts a bool or CA bundle path.
    """

    url: str
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)
    token: str | None = field(default=None, repr=False)
    verify: bool | str = True
    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    allow_http: bool = False
    expected_fsid: str | None = None

    def __post_init__(self):
        if not isinstance(self.url, str) or re.search(r"[\x00-\x20\x7f]", self.url):
            raise ConfigurationError("url must be a Dashboard root URL.")
        try:
            parsed = urlsplit(self.url)
            port = parsed.port
        except ValueError:
            raise ConfigurationError("Invalid Dashboard URL.") from None
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or port == 0
            or unquote(parsed.path).rstrip("/").endswith("/api")
        ):
            raise ConfigurationError("url must be a Dashboard root without credentials or /api.")
        validate_path(parsed.path or "/")
        if not isinstance(self.allow_http, bool):
            raise ConfigurationError("allow_http must be a boolean.")
        if parsed.scheme == "http" and not self.allow_http:
            raise ConfigurationError("Plain HTTP requires allow_http: true.")
        for name in ("username", "password", "token"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ConfigurationError(f"{name} must be a non-empty string.")
        if self.token is not None:
            if self.username is not None or self.password is not None:
                raise ConfigurationError("Use token OR username/password, not both.")
            if re.search(r"\s|[^\x21-\x7e]", self.token):
                raise ConfigurationError("token contains invalid header characters.")
        elif self.username is None or self.password is None:
            raise ConfigurationError("Provide token or both username and password.")
        if not isinstance(self.verify, bool) and not (
            isinstance(self.verify, str) and self.verify.strip()
        ):
            raise ConfigurationError("verify must be a boolean or a CA bundle path.")
        for name in ("connect_timeout", "read_timeout"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ConfigurationError(f"{name} must be a positive finite number.")
        if self.expected_fsid is not None:
            if not isinstance(self.expected_fsid, str):
                raise ConfigurationError("expected_fsid must be a UUID string.")
            try:
                normalized_fsid = str(uuid.UUID(self.expected_fsid))
            except ValueError:
                raise ConfigurationError("expected_fsid must be a UUID string.") from None
            object.__setattr__(self, "expected_fsid", normalized_fsid)
        object.__setattr__(self, "url", self.url.rstrip("/"))


def load_profile(opts, pillar, profile="default"):
    """Read ``ceph:profiles:<profile>``; a pillar profile replaces an opts profile.

    Profiles are never merged, preventing credentials from one source being sent
    to an endpoint from another. Callers explicitly provide their loader context.
    """
    if not isinstance(profile, str) or not profile:
        raise ConfigurationError("profile must be a non-empty string.")
    for source in (pillar, opts):
        if not isinstance(source, Mapping):
            raise ConfigurationError("Ceph configuration source must be a mapping.")
        ceph = source.get("ceph", {})
        if not isinstance(ceph, Mapping) or not isinstance(ceph.get("profiles", {}), Mapping):
            raise ConfigurationError("ceph:profiles must be a mapping.")
        profiles = ceph.get("profiles", {})
        if profile in profiles:
            settings = profiles[profile]
            if not isinstance(settings, Mapping):
                raise ConfigurationError("Ceph profile must be a mapping.")
            if set(settings) - {item.name for item in fields(ConnectionConfig)}:
                raise ConfigurationError("Ceph profile contains unsupported settings.")
            if "url" not in settings:
                raise ConfigurationError("Ceph profile requires url.")
            return ConnectionConfig(**settings)
    raise ConfigurationError("Requested Ceph profile is not configured.")
