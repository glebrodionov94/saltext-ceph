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

from ._storage_policy import STORAGE_KINDS
from ._storage_policy import StoragePolicyError
from ._storage_policy import StorageWritePolicy
from ._storage_policy import validate_resource as validate_storage_resource

ENV_PREFIX = "CEPH_TEST_"
_TRUE_VALUES = frozenset(("1", "true", "yes", "on"))
_FALSE_VALUES = frozenset(("0", "false", "no", "off"))
_FEATURE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_GLOB_RE = re.compile(r"[*?\[\]]")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}")
_DEVICE_PATH_RE = re.compile(
    "|".join(
        (
            r"/dev/[A-Za-z0-9][A-Za-z0-9_.:+-]{0,254}",
            r"/dev/disk/by-id/[A-Za-z0-9][A-Za-z0-9_.:+-]{0,400}",
        )
    )
)
_WRITE_METHODS = frozenset(("POST", "PUT", "PATCH", "DELETE"))
_METADATA_COLLECTIONS = {"role": "/api/role", "user": "/api/user"}
_INFRASTRUCTURE_KINDS = (
    frozenset(
        (
            "device",
            "device-id",
            "host",
            "osd",
            "service",
        )
    )
    | STORAGE_KINDS
)
_CORE_SERVICE_TYPES = frozenset(("mon", "mgr", "osd"))


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
        expected_fsid = self.require_destructive_gate()
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

    def require_destructive_gate(self):
        """Require the destructive flags and exact cluster confirmation.

        Resource membership remains a separate check because infrastructure
        identifiers such as a newly allocated OSD ID are discovered at run
        time.  A transport write is still impossible without an active lease
        whose exact identifiers pass :meth:`require_destructive`.
        """
        expected_fsid = self.require_mutation()
        if not self.destructive:
            raise LiveConfigurationError("Destructive live tests require --ceph-live-destructive.")
        if self.destructive_confirmation_fsid is None or not hmac.compare_digest(
            self.destructive_confirmation_fsid, expected_fsid
        ):
            raise LiveConfigurationError(
                "CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID must exactly match CEPH_TEST_EXPECTED_FSID."
            )
        return expected_fsid


class GuardedLiveClient:
    """Restrict live writes to exact resources leased by one test.

    The underlying client still verifies ``expected_fsid``. This proxy adds a
    capability boundary around the actual HTTP method, path, and JSON body.
    Infrastructure writes additionally need an active lease.  Route rules bind
    its allowlisted identifiers to the HTTP method, path, API version, query,
    and body before the underlying client can observe the request.
    """

    def __init__(self, client, settings, level="live", destructive_resources=()):
        self._client = client
        self._settings = settings
        self._level = level
        self._owned = None
        self._leased = None
        self._leased_inventory = {}
        self._authorized_osd_create = None
        self._claimed_osds = frozenset()
        resources = tuple(destructive_resources)
        if level == "destructive":
            settings.require_destructive_gate()
            if resources:
                settings.require_destructive(*resources)
        elif level == "mutate":
            settings.require_mutation()
            if resources:
                raise LiveConfigurationError("Metadata tests cannot declare destructive resources.")
        elif level != "live" or resources:
            raise LiveConfigurationError("Invalid live-test request policy.")
        self._declared_resources = frozenset(resources)

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

    @staticmethod
    def _infrastructure_identity(resource):
        """Parse one canonical, non-wildcard infrastructure capability."""
        if not isinstance(resource, str) or ":" not in resource:
            raise LiveConfigurationError("Infrastructure leases require typed resource IDs.")
        kind, identifier = resource.split(":", 1)
        if kind not in _INFRASTRUCTURE_KINDS or not identifier:
            raise LiveConfigurationError("Infrastructure lease resource type is unsupported.")
        if (
            _CONTROL_RE.search(identifier)
            or _GLOB_RE.search(identifier)
            or any(character.isspace() for character in identifier)
        ):
            raise LiveConfigurationError("Infrastructure lease resource ID must be exact.")
        if kind in ("host", "service"):
            if not _IDENTIFIER_RE.fullmatch(identifier):
                raise LiveConfigurationError("Infrastructure lease identifier is invalid.")
        elif kind == "osd":
            if not identifier.isdecimal() or str(int(identifier)) != identifier:
                raise LiveConfigurationError("OSD lease identifier must be canonical.")
        elif kind in ("device", "device-id"):
            if ":" not in identifier:
                raise LiveConfigurationError("Device leases must include an exact host.")
            hostname, value = identifier.split(":", 1)
            if not _IDENTIFIER_RE.fullmatch(hostname) or not value:
                raise LiveConfigurationError("Device lease identifier is invalid.")
            if kind == "device" and not _DEVICE_PATH_RE.fullmatch(value):
                raise LiveConfigurationError("Device lease requires a canonical /dev path.")
            if kind == "device-id" and (
                len(value) > 512 or value in (".", "..") or "/" in value or "\\" in value
            ):
                raise LiveConfigurationError("Device identity lease is invalid.")
        else:
            try:
                validate_storage_resource(kind, identifier)
            except StoragePolicyError as exc:
                raise LiveConfigurationError(str(exc)) from None
        return kind, identifier

    @classmethod
    def _inventory_devices(cls, inventory, leased):
        """Validate same-test device availability evidence for OSD creation."""
        if inventory is None:
            return {}
        if not isinstance(inventory, Mapping):
            raise LiveConfigurationError("OSD inventory evidence must be a mapping.")
        hostname = inventory.get("name", inventory.get("hostname"))
        if not isinstance(hostname, str) or f"host:{hostname}" not in leased:
            raise LiveConfigurationError("OSD inventory host is not part of the active lease.")
        devices = inventory.get("devices")
        if not isinstance(devices, list):
            raise LiveConfigurationError("OSD inventory evidence has no device list.")
        available = {}
        for device in devices:
            if not isinstance(device, Mapping):
                raise LiveConfigurationError("OSD inventory contains an invalid device record.")
            path = device.get("path")
            if not isinstance(path, str) or not _DEVICE_PATH_RE.fullmatch(path):
                continue
            path_resource = f"device:{hostname}:{path}"
            if path_resource not in leased:
                continue
            if device.get("available") is not True or device.get("osd_ids") != []:
                raise LiveConfigurationError("Leased OSD device is not empty and available.")
            rejected = device.get("rejected_reasons", [])
            if not isinstance(rejected, list) or rejected:
                raise LiveConfigurationError("Leased OSD device has rejection reasons.")
            device_id = device.get("device_id")
            if device_id not in (None, ""):
                if not isinstance(device_id, str):
                    raise LiveConfigurationError("Leased OSD device identity is invalid.")
                identity_resource = f"device-id:{hostname}:{device_id}"
                cls._infrastructure_identity(identity_resource)
                if identity_resource not in leased:
                    raise LiveConfigurationError(
                        "Available OSD device identity is absent from the active lease."
                    )
            available[(hostname, path)] = device_id or None
        return available

    @contextmanager
    def infrastructure_lease(self, *resources, device_inventory=None):
        """Lease exact allowlisted infrastructure for one state lifecycle.

        OSD creation also passes the result of a fresh host inventory GET.  A
        path is eligible only when that evidence reports it available, without
        OSD IDs or rejection reasons, and its device ID is leased when present.
        """
        if self._level != "destructive":
            raise LiveConfigurationError(
                "Infrastructure ownership requires a destructive live test."
            )
        if self._leased is not None:
            raise LiveConfigurationError("A live client can hold only one infrastructure lease.")
        parsed = tuple(self._infrastructure_identity(resource) for resource in resources)
        if len(parsed) != len(set(parsed)):
            raise LiveConfigurationError("Infrastructure lease resources must be unique.")
        self._settings.require_destructive(*resources)
        leased = frozenset(resources)
        if self._declared_resources and not leased.issubset(self._declared_resources):
            raise LiveConfigurationError(
                "Infrastructure lease exceeds the resources declared by this test."
            )
        inventory_devices = self._inventory_devices(device_inventory, leased)
        self._leased = leased
        self._leased_inventory = inventory_devices
        self._authorized_osd_create = None
        self._claimed_osds = frozenset()
        try:
            yield self
        finally:
            self._claimed_osds = frozenset()
            self._authorized_osd_create = None
            self._leased_inventory = {}
            self._leased = None

    @staticmethod
    def _inventory_osd_id(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, str) and value.isdecimal() and str(int(value)) == value:
            return int(value)
        return None

    def claim_created_osds(self, inventory):
        """Derive one OSD lease from post-create inventory provenance.

        This is the sole exception to external OSD allowlisting.  It applies
        only after a successful, guarded drive-group POST in the same active
        lease and only to the single OSD now reported on that exact device with
        the expected ``osdspec_affinity``.
        """
        if self._leased is None or self._authorized_osd_create is None:
            raise LiveConfigurationError("No successful guarded OSD creation can be claimed.")
        if self._claimed_osds:
            raise LiveConfigurationError("Guarded OSD creation has already been claimed.")
        if not isinstance(inventory, Mapping):
            raise LiveConfigurationError("Post-create OSD inventory must be a mapping.")
        hostname, path, service_id = self._authorized_osd_create
        inventory_hostname = inventory.get("name", inventory.get("hostname"))
        devices = inventory.get("devices")
        if inventory_hostname != hostname or not isinstance(devices, list):
            raise LiveConfigurationError("Post-create OSD inventory does not match its host.")
        matches = [
            item for item in devices if isinstance(item, Mapping) and item.get("path") == path
        ]
        if len(matches) != 1:
            raise LiveConfigurationError("Post-create OSD inventory does not match one device.")
        device = matches[0]
        initial_device_id = self._leased_inventory.get((hostname, path))
        current_device_id = device.get("device_id") or None
        if current_device_id != initial_device_id:
            raise LiveConfigurationError("Post-create OSD device identity changed.")
        osd_ids = device.get("osd_ids")
        if not isinstance(osd_ids, list) or len(osd_ids) != 1:
            raise LiveConfigurationError("Post-create device must identify exactly one OSD.")
        osd_id = self._inventory_osd_id(osd_ids[0])
        if osd_id is None:
            raise LiveConfigurationError("Post-create OSD identifier is not canonical.")
        lvs = device.get("lvs")
        if (
            not isinstance(lvs, list)
            or not lvs
            or not all(isinstance(item, Mapping) for item in lvs)
        ):
            raise LiveConfigurationError("Post-create device has no valid LVM provenance.")
        lv_ids = {self._inventory_osd_id(item.get("osd_id")) for item in lvs}
        if lv_ids != {osd_id} or any(item.get("osdspec_affinity") != service_id for item in lvs):
            raise LiveConfigurationError("Post-create OSD LVM affinity does not match its lease.")
        resource = f"osd:{osd_id}"
        self._leased = self._leased | {resource}
        self._claimed_osds = frozenset((resource,))
        return (osd_id,)

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

    @staticmethod
    def _exact_mapping(value, required, optional=()):
        if not isinstance(value, Mapping):
            return False
        keys = set(value)
        return set(required).issubset(keys) and keys.issubset(set(required) | set(optional))

    def _require_leased(self, resource):
        if self._leased is None:
            raise LiveConfigurationError(
                "Destructive live write has no active infrastructure lease."
            )
        if resource not in self._leased:
            raise LiveConfigurationError("Destructive live write exceeds its infrastructure lease.")

    @staticmethod
    def _validate_labels(labels):
        return (
            isinstance(labels, list)
            and all(isinstance(label, str) and _IDENTIFIER_RE.fullmatch(label) for label in labels)
            and len(labels) == len(set(labels))
        )

    def _authorize_host_create(self, api_version, params, data):
        if (
            api_version != "0.1"
            or params is not None
            or not self._exact_mapping(data, ("hostname",), ("addr", "labels", "status"))
        ):
            return False
        hostname = data["hostname"]
        if not isinstance(hostname, str) or not _IDENTIFIER_RE.fullmatch(hostname):
            return False
        self._require_leased(f"host:{hostname}")
        if "addr" in data and (
            not isinstance(data["addr"], str)
            or not data["addr"]
            or len(data["addr"]) > 255
            or _CONTROL_RE.search(data["addr"])
        ):
            return False
        if "labels" in data and not self._validate_labels(data["labels"]):
            return False
        return "status" not in data or data["status"] == "maintenance"

    def _authorize_host(self, method, path, api_version, params, data):
        if method == "POST" and path == "/api/host":
            return self._authorize_host_create(api_version, params, data)

        if not path.startswith("/api/host/"):
            return False
        hostname = next(
            (
                resource.removeprefix("host:")
                for resource in self._leased or ()
                if resource.startswith("host:")
                and path == f"/api/host/{quote(resource.removeprefix('host:'), safe='')}"
            ),
            None,
        )
        if hostname is None:
            return False
        self._require_leased(f"host:{hostname}")
        if method == "DELETE":
            return api_version == "1.0" and params is None and data is None
        if method != "PUT" or api_version != "0.1" or params is not None:
            return False
        if self._exact_mapping(data, ("update_labels", "labels")):
            return data["update_labels"] is True and self._validate_labels(data["labels"])
        if self._exact_mapping(data, ("maintenance",), ("force",)):
            return data["maintenance"] is True and (
                "force" not in data or isinstance(data["force"], bool)
            )
        if self._exact_mapping(data, ("drain",)):
            return data["drain"] is True
        return False

    def _validate_placement(self, placement):
        if not self._exact_mapping(placement, ("hosts",), ("count",)):
            return False
        hosts = placement["hosts"]
        if (
            not isinstance(hosts, list)
            or not hosts
            or not all(isinstance(host, str) and _IDENTIFIER_RE.fullmatch(host) for host in hosts)
            or len(hosts) != len(set(hosts))
        ):
            return False
        for hostname in hosts:
            self._require_leased(f"host:{hostname}")
        if "count" in placement and (
            isinstance(placement["count"], bool)
            or not isinstance(placement["count"], int)
            or not 1 <= placement["count"] <= len(hosts)
        ):
            return False
        return True

    @staticmethod
    def _service_identity(service_name, *, allow_osd=False):
        if not isinstance(service_name, str) or not _IDENTIFIER_RE.fullmatch(service_name):
            return None
        service_type, separator, service_id = service_name.partition(".")
        if not separator or not service_id.startswith("saltext-ci-"):
            return None
        if service_type in _CORE_SERVICE_TYPES and not (allow_osd and service_type == "osd"):
            return None
        if not _IDENTIFIER_RE.fullmatch(service_type) or not _IDENTIFIER_RE.fullmatch(service_id):
            return None
        return service_type, service_id

    def _validate_service_spec(self, service_name, spec):
        identity = self._service_identity(service_name)
        if identity is None or not self._exact_mapping(
            spec,
            ("service_type", "service_id", "placement"),
            ("service_name", "unmanaged"),
        ):
            return False
        service_type, service_id = identity
        if spec["service_type"] != service_type or spec["service_id"] != service_id:
            return False
        if "service_name" in spec and spec["service_name"] != service_name:
            return False
        if "unmanaged" in spec and not isinstance(spec["unmanaged"], bool):
            return False
        return self._validate_placement(spec["placement"])

    def _authorize_service(self, method, path, api_version, params, data):
        if api_version != "1.0" or params is not None:
            return False
        if method == "POST" and path == "/api/service":
            if not self._exact_mapping(data, ("service_name", "service_spec")):
                return False
            service_name = data["service_name"]
            self._require_leased(f"service:{service_name}")
            return self._validate_service_spec(service_name, data["service_spec"])

        service_name = next(
            (
                resource.removeprefix("service:")
                for resource in self._leased or ()
                if resource.startswith("service:")
                and path == f"/api/service/{quote(resource.removeprefix('service:'), safe='')}"
            ),
            None,
        )
        identity = (
            None if service_name is None else self._service_identity(service_name, allow_osd=True)
        )
        if identity is None:
            return False
        self._require_leased(f"service:{service_name}")
        if method == "DELETE":
            return data is None
        if method == "PUT" and self._exact_mapping(data, ("service_spec",)):
            if identity[0] == "osd":
                spec = data["service_spec"]
                return (
                    self._validate_drive_group(spec)
                    and spec["service_id"] == identity[1]
                    and spec.get("unmanaged") is True
                )
            return self._validate_service_spec(service_name, data["service_spec"])
        return False

    def _validate_drive_group(self, spec):
        if not self._exact_mapping(
            spec,
            ("service_type", "service_id", "placement", "data_devices"),
            ("encrypted", "unmanaged"),
        ):
            return False
        if spec["service_type"] != "osd" or not isinstance(spec["service_id"], str):
            return False
        service_name = f"osd.{spec['service_id']}"
        if self._service_identity(service_name, allow_osd=True) != ("osd", spec["service_id"]):
            return False
        self._require_leased(f"service:{service_name}")
        if not self._validate_placement(spec["placement"]):
            return False
        hosts = spec["placement"]["hosts"]
        if len(hosts) != 1 or "count" in spec["placement"]:
            return False
        devices = spec["data_devices"]
        if not self._exact_mapping(devices, ("paths",)):
            return False
        paths = devices["paths"]
        if not isinstance(paths, list) or len(paths) != 1:
            return False
        path = paths[0]
        if not isinstance(path, str) or not _DEVICE_PATH_RE.fullmatch(path):
            return False
        hostname = hosts[0]
        self._require_leased(f"device:{hostname}:{path}")
        if (hostname, path) not in self._leased_inventory:
            raise LiveConfigurationError(
                "OSD creation requires fresh available-device inventory evidence."
            )
        return ("encrypted" not in spec or isinstance(spec["encrypted"], bool)) and (
            "unmanaged" not in spec or isinstance(spec["unmanaged"], bool)
        )

    def _authorize_osd(self, method, path, api_version, params, data):
        if api_version != "1.0":
            return False
        if method == "POST" and path == "/api/osd":
            if self._authorized_osd_create is not None:
                return False
            if params is not None or not self._exact_mapping(
                data, ("method", "data", "tracking_id")
            ):
                return False
            groups = data["data"]
            if data["method"] != "drive_groups" or not isinstance(groups, list) or len(groups) != 1:
                return False
            if not self._validate_drive_group(groups[0]) or "unmanaged" in groups[0]:
                return False
            service_name = f"osd.{groups[0]['service_id']}"
            return data["tracking_id"] == service_name

        osd_id = next(
            (
                resource.removeprefix("osd:")
                for resource in self._leased or ()
                if resource.startswith("osd:")
                and path == f"/api/osd/{resource.removeprefix('osd:')}"
            ),
            None,
        )
        if osd_id is None:
            return False
        self._require_leased(f"osd:{osd_id}")
        if method == "DELETE":
            return (
                data is None
                and self._exact_mapping(params, ("preserve_id", "force"))
                and isinstance(params["preserve_id"], bool)
                and isinstance(params["force"], bool)
            )
        if method == "PUT":
            return (
                params is None
                and self._exact_mapping(data, ("device_class",))
                and (
                    isinstance(data["device_class"], str)
                    and len(data["device_class"]) <= 64
                    and re.fullmatch(r"[A-Za-z0-9_.-]*", data["device_class"]) is not None
                )
            )
        return False

    def _authorize_infrastructure(self, method, path, api_version, params, data):
        if self._leased is None:
            raise LiveConfigurationError(
                "Destructive live write has no active infrastructure lease."
            )
        if path == "/api/host" or path.startswith("/api/host/"):
            allowed = self._authorize_host(method, path, api_version, params, data)
        elif path == "/api/service" or path.startswith("/api/service/"):
            allowed = self._authorize_service(method, path, api_version, params, data)
        elif path == "/api/osd" or path.startswith("/api/osd/"):
            allowed = self._authorize_osd(method, path, api_version, params, data)
        else:
            try:
                allowed = StorageWritePolicy(self._leased).authorize(
                    method, path, api_version, params, data
                )
            except StoragePolicyError as exc:
                raise LiveConfigurationError(str(exc)) from None
        if not allowed:
            raise LiveConfigurationError(
                "Destructive live write method, route, version, query, or body is not authorized."
            )

    def request(self, method, path, *, api_version, params=None, data=None):
        """Authorize the concrete request before forwarding it to Dashboard."""
        normalized_method = method.upper() if isinstance(method, str) else method
        if normalized_method in _WRITE_METHODS:
            if self._level == "live":
                raise LiveConfigurationError("Read-only live tests cannot send HTTP mutations.")
            if self._level == "destructive":
                self._authorize_infrastructure(normalized_method, path, api_version, params, data)
            else:
                self._authorize_metadata(normalized_method, path, data)
        response = self._client.request(
            method,
            path,
            api_version=api_version,
            params=params,
            data=data,
        )
        if self._level == "destructive" and normalized_method == "POST" and path == "/api/osd":
            group = data["data"][0]
            self._authorized_osd_create = (
                group["placement"]["hosts"][0],
                group["data_devices"]["paths"][0],
                group["service_id"],
            )
        return response


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
