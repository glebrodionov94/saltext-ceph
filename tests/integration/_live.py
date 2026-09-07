"""Safety boundary for opt-in tests against a real Ceph cluster.

This module intentionally contains no pytest hooks and performs no network I/O.
It translates an explicit environment into a redacted connection configuration
and enforces the additional gates used by mutating and destructive tests.

``mutate`` includes exact cleanup of a metadata resource which the current test
created under its reserved UUID-backed prefix (for example a Dashboard role,
user, or CephX identity). ``destructive`` is reserved for existing or physical
cluster infrastructure: OSDs, hosts, pools, filesystems, and service specs. Such
tests must declare every concrete resource identifier in the allowlist.
"""

import hmac
import math
import os
import re
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import quote

from saltext.ceph.utils.ceph.config import ConnectionConfig
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.secret_file import read as read_secret_file

ENV_PREFIX = "CEPH_TEST_"
_TRUE_VALUES = frozenset(("1", "true", "yes", "on"))
_FALSE_VALUES = frozenset(("0", "false", "no", "off"))
_FEATURE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_GLOB_RE = re.compile(r"[*?\[\]]")
_WRITE_METHODS = frozenset(("POST", "PUT", "PATCH", "DELETE"))
_METADATA_COLLECTIONS = {"role": "/api/role", "user": "/api/user"}


class LiveConfigurationError(ValueError):
    """A live-test gate is missing or unsafe.

    Messages name configuration keys, but never include their values or file
    paths. This keeps pytest tracebacks useful without disclosing credentials.
    """


def _value(environ, name, *, strip=False):
    """Read ``name`` or ``name_FILE`` without exposing either value."""
    file_name = f"{name}_FILE"
    has_value = name in environ
    has_file = file_name in environ
    if has_value and has_file:
        raise LiveConfigurationError(f"Set only one of {name} and {file_name}.")
    if has_file:
        source = environ[file_name]
        if not isinstance(source, str) or not source:
            raise LiveConfigurationError(f"{file_name} must name a safe absolute file.")
        try:
            value = read_secret_file(source).rstrip("\r\n")
        except ConfigurationError:
            raise LiveConfigurationError(
                f"{file_name} must name a readable, safe absolute file."
            ) from None
    elif has_value:
        value = environ[name]
    else:
        return None
    if not isinstance(value, str) or not value:
        raise LiveConfigurationError(f"{name} must not be empty.")
    return value.strip() if strip else value


def _boolean(value, name, *, default=False):
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise LiveConfigurationError(f"{name} must be a boolean value.")


def _positive_float(value, name, default):
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise LiveConfigurationError(f"{name} must be a positive number.") from None
    if not math.isfinite(parsed) or parsed <= 0:
        raise LiveConfigurationError(f"{name} must be a positive number.")
    return parsed


def _verify(value):
    if value is None:
        return True
    normalized = value.strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    if not value.strip():
        raise LiveConfigurationError("CEPH_TEST_VERIFY must be a boolean or CA bundle path.")
    return value.strip()


def _canonical_fsid(value, name):
    if value is None:
        return None
    try:
        normalized = str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        raise LiveConfigurationError(f"{name} must be a canonical UUID.") from None
    if value != normalized:
        raise LiveConfigurationError(f"{name} must be a canonical UUID.")
    return normalized


def _features(value):
    if value is None:
        return frozenset()
    parsed = frozenset(part.casefold() for part in re.split(r"[,\s]+", value.strip()) if part)
    if not parsed or any(not _FEATURE_RE.fullmatch(part) for part in parsed):
        raise LiveConfigurationError(
            "CEPH_TEST_FEATURES must contain comma-separated feature identifiers."
        )
    return parsed


def _allowlist(value):
    if value is None:
        return frozenset()
    resources = frozenset(part.strip() for part in re.split(r"[,\r\n]+", value) if part.strip())
    if not resources:
        raise LiveConfigurationError("CEPH_TEST_DESTRUCTIVE_ALLOWLIST must not be empty.")
    for resource in resources:
        if (
            len(resource) > 512
            or _CONTROL_RE.search(resource)
            or any(char.isspace() for char in resource)
            or _GLOB_RE.search(resource)
        ):
            raise LiveConfigurationError(
                "CEPH_TEST_DESTRUCTIVE_ALLOWLIST accepts exact resource identifiers only."
            )
    return resources


def validate_flag_hierarchy(*, live, mutate, destructive):
    """Require every increasingly dangerous command-line gate explicitly."""
    if mutate and not live:
        raise LiveConfigurationError("--ceph-live-mutate also requires --ceph-live.")
    if destructive and not mutate:
        raise LiveConfigurationError(
            "--ceph-live-destructive also requires --ceph-live-mutate and --ceph-live."
        )


@dataclass(frozen=True, repr=False)
class LiveSettings:
    """Validated live-test settings with a deliberately redacted repr."""

    connection: ConnectionConfig
    mutate: bool = False
    destructive: bool = False
    features: frozenset[str] = frozenset()
    destructive_confirmation_fsid: str | None = None
    destructive_allowlist: frozenset[str] = frozenset()

    @property
    def config(self):
        """Compatibility alias for code which calls this the client config."""
        return self.connection

    @property
    def live(self):
        """The settings object can only exist when the read-only gate is open."""
        return True

    @property
    def flags(self):
        """Return a new, non-secret mapping of enabled command-line gates."""
        return {"live": True, "mutate": self.mutate, "destructive": self.destructive}

    @property
    def expected_fsid(self):
        """Return the normalized cluster identity used for write protection."""
        return self.connection.expected_fsid

    def __repr__(self):
        return (
            "LiveSettings("
            f"mutate={self.mutate!r}, destructive={self.destructive!r}, "
            f"features={sorted(self.features)!r}, "
            f"allowlisted_resources={len(self.destructive_allowlist)})"
        )

    def require_features(self, *features):
        """Return unavailable feature identifiers, normalized for comparisons."""
        required = frozenset(str(feature).casefold() for feature in features)
        return required - self.features

    def has_feature(self, feature):
        """Whether a named optional service was declared for this test cluster."""
        return isinstance(feature, str) and feature.casefold() in self.features

    def require_mutation(self):
        """Enforce the mutation flag and expected-cluster identity.

        Callers which clean up test-owned metadata must still prove that an
        exact UUID-backed name was absent before they created it and delete only
        that same name.
        """
        if not self.mutate:
            raise LiveConfigurationError("Live mutation requires --ceph-live-mutate.")
        if self.expected_fsid is None:
            raise LiveConfigurationError(
                "Live mutation requires CEPH_TEST_EXPECTED_FSID or its _FILE variant."
            )
        return self.expected_fsid

    def require_destructive(self, *resources):
        """Gate changes to existing or physical cluster infrastructure."""
        expected_fsid = self.require_mutation()
        if not self.destructive:
            raise LiveConfigurationError("Destructive live tests require --ceph-live-destructive.")
        if self.destructive_confirmation_fsid is None or not hmac.compare_digest(
            self.destructive_confirmation_fsid, expected_fsid
        ):
            raise LiveConfigurationError(
                "CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID must exactly match CEPH_TEST_EXPECTED_FSID."
            )
        if not resources:
            raise LiveConfigurationError(
                "A destructive live test must declare every affected resource identifier."
            )
        if any(
            not isinstance(resource, str)
            or not resource
            or _CONTROL_RE.search(resource)
            or _GLOB_RE.search(resource)
            for resource in resources
        ):
            raise LiveConfigurationError(
                "Destructive resources must be exact, non-empty string identifiers."
            )
        requested = frozenset(resources)
        if not requested.issubset(self.destructive_allowlist):
            raise LiveConfigurationError(
                "A destructive resource is absent from CEPH_TEST_DESTRUCTIVE_ALLOWLIST."
            )
        return expected_fsid


class GuardedLiveClient:
    """Restrict live writes to metadata explicitly owned by one test.

    The underlying client still verifies ``expected_fsid``. This proxy adds a
    capability boundary around the actual HTTP method, path, and JSON body.
    Destructive writes fail closed until their test supplies a dedicated route
    rule that can bind the configured allowlist to the affected Ceph resource.
    """

    def __init__(self, client, settings, level="live", destructive_resources=()):
        self._client = client
        self._settings = settings
        self._level = level
        self._owned = None
        resources = tuple(destructive_resources)
        if level == "destructive":
            settings.require_destructive(*resources)
        elif level == "mutate":
            settings.require_mutation()
            if resources:
                raise LiveConfigurationError("Metadata tests cannot declare destructive resources.")
        elif level != "live" or resources:
            raise LiveConfigurationError("Invalid live-test request policy.")

    @property
    def config(self):
        """Expose the connection settings expected by typed adapters."""
        return self._client.config

    @property
    def closed(self):
        """Whether the underlying HTTP session is closed."""
        return self._client.closed

    def check(self):
        """Validate this process's own Dashboard session without a resource write."""
        return self._client.check()

    @staticmethod
    def _identity(kind, identifier, ownership_marker):
        if kind not in _METADATA_COLLECTIONS:
            raise LiveConfigurationError("Unsupported live metadata resource kind.")
        if not isinstance(identifier, str) or not isinstance(ownership_marker, str):
            raise LiveConfigurationError("Metadata identity and ownership marker must be strings.")
        prefix = f"saltext-ci-{kind}-"
        if not identifier.startswith(prefix):
            raise LiveConfigurationError("Metadata identity must use the reserved test prefix.")
        suffix = identifier[len(prefix) :]
        try:
            canonical = str(uuid.UUID(suffix))
        except (AttributeError, TypeError, ValueError):
            raise LiveConfigurationError(
                "Metadata identity must end in a canonical UUID."
            ) from None
        if suffix != canonical or ownership_marker != f"saltext-ci-owner:{canonical}":
            raise LiveConfigurationError(
                "Metadata identity and ownership marker must contain the same canonical UUID."
            )
        return kind, identifier, ownership_marker

    @contextmanager
    def owned_metadata(self, kind, identifier, ownership_marker):
        """Lease one absent UUID-named role or user for a single test lifecycle."""
        if self._level != "mutate":
            raise LiveConfigurationError(
                "Metadata ownership requires a test marked ceph_live_mutate."
            )
        if self._owned is not None:
            raise LiveConfigurationError("A live client can lease only one metadata resource.")
        self._owned = self._identity(kind, identifier, ownership_marker)
        try:
            yield self
        finally:
            self._owned = None

    def _authorize_metadata(self, method, path, data):
        if self._owned is None:
            raise LiveConfigurationError("Live metadata write has no active ownership lease.")
        kind, identifier, marker = self._owned
        collection = _METADATA_COLLECTIONS[kind]
        item_path = f"{collection}/{quote(identifier, safe='')}"
        identity_field = "name" if kind == "role" else "username"
        marker_field = "description" if kind == "role" else "name"
        if method == "POST":
            valid_target = path == collection and isinstance(data, Mapping)
            valid_target = valid_target and data.get(identity_field) == identifier
        elif method in ("PUT", "DELETE"):
            valid_target = path == item_path
        else:
            valid_target = False
        if not valid_target:
            raise LiveConfigurationError(
                "Live metadata write method, path, or identity does not match its lease."
            )
        if method in ("POST", "PUT"):
            if not isinstance(data, Mapping) or data.get(marker_field) not in (
                marker,
                f"{marker}:updated",
            ):
                raise LiveConfigurationError(
                    "Live metadata write does not preserve its ownership marker."
                )

    def request(self, method, path, *, api_version, params=None, data=None):
        """Authorize the concrete request before forwarding it to Dashboard."""
        normalized_method = method.upper() if isinstance(method, str) else method
        if normalized_method in _WRITE_METHODS:
            if self._level == "live":
                raise LiveConfigurationError("Read-only live tests cannot send HTTP mutations.")
            if self._level == "destructive":
                raise LiveConfigurationError(
                    "No destructive live HTTP operations have an exact route rule yet."
                )
            self._authorize_metadata(normalized_method, path, data)
        return self._client.request(
            method,
            path,
            api_version=api_version,
            params=params,
            data=data,
        )


def load_settings(
    *,
    live,
    mutate=False,
    destructive=False,
    environ: Mapping[str, str] | None = None,
):
    """Build live settings from an explicit mapping, defaulting to ``os.environ``."""
    validate_flag_hierarchy(live=live, mutate=mutate, destructive=destructive)
    if not live:
        raise LiveConfigurationError("Live settings require --ceph-live.")
    source = os.environ if environ is None else environ
    if not isinstance(source, Mapping):
        raise LiveConfigurationError("Live-test environment must be a mapping.")

    url = _value(source, f"{ENV_PREFIX}URL", strip=True)
    if url is None:
        raise LiveConfigurationError("CEPH_TEST_URL or CEPH_TEST_URL_FILE is required.")
    username = _value(source, f"{ENV_PREFIX}USERNAME")
    password = _value(source, f"{ENV_PREFIX}PASSWORD")
    token = _value(source, f"{ENV_PREFIX}TOKEN")
    expected_fsid = _canonical_fsid(
        _value(source, f"{ENV_PREFIX}EXPECTED_FSID", strip=True),
        "CEPH_TEST_EXPECTED_FSID",
    )
    confirmation_fsid = _canonical_fsid(
        _value(source, f"{ENV_PREFIX}DESTRUCTIVE_CONFIRM_FSID", strip=True),
        "CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID",
    )
    destructive_allowlist = _allowlist(_value(source, f"{ENV_PREFIX}DESTRUCTIVE_ALLOWLIST"))

    try:
        connection = ConnectionConfig(
            url=url,
            username=username,
            password=password,
            token=token,
            verify=_verify(_value(source, f"{ENV_PREFIX}VERIFY", strip=True)),
            connect_timeout=_positive_float(
                _value(source, f"{ENV_PREFIX}CONNECT_TIMEOUT", strip=True),
                "CEPH_TEST_CONNECT_TIMEOUT",
                5.0,
            ),
            read_timeout=_positive_float(
                _value(source, f"{ENV_PREFIX}READ_TIMEOUT", strip=True),
                "CEPH_TEST_READ_TIMEOUT",
                30.0,
            ),
            allow_http=_boolean(
                _value(source, f"{ENV_PREFIX}ALLOW_HTTP", strip=True),
                "CEPH_TEST_ALLOW_HTTP",
            ),
            expected_fsid=expected_fsid,
        )
    except ConfigurationError as exc:
        raise LiveConfigurationError(str(exc)) from None

    settings = LiveSettings(
        connection=connection,
        mutate=mutate,
        destructive=destructive,
        features=_features(_value(source, f"{ENV_PREFIX}FEATURES", strip=True)),
        destructive_confirmation_fsid=confirmation_fsid,
        destructive_allowlist=destructive_allowlist,
    )
    if destructive:
        # Resource membership is checked by each destructive test once it has
        # declared the concrete identifiers it will touch.
        settings.require_mutation()
        if confirmation_fsid is None or not hmac.compare_digest(
            confirmation_fsid, settings.expected_fsid
        ):
            raise LiveConfigurationError(
                "CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID must exactly match CEPH_TEST_EXPECTED_FSID."
            )
        if not destructive_allowlist:
            raise LiveConfigurationError(
                "Destructive live tests require CEPH_TEST_DESTRUCTIVE_ALLOWLIST."
            )
    elif mutate:
        settings.require_mutation()
    return settings
