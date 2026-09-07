"""Fail-closed authorization for destructive storage lifecycle tests.

The live state tests deliberately exercise real Dashboard writes.  This module
binds every permitted write to an exact, runtime-leased test resource and to the
small request shape used by those tests.  It is kept independent of pytest so
the policy can be covered exhaustively with fast unit tests.
"""

import re
from collections.abc import Mapping
from urllib.parse import quote

STORAGE_KINDS = frozenset(
    (
        "bucket",
        "cephfs-group",
        "cephfs-snapshot",
        "cephfs-subvolume",
        "fs",
        "image",
        "namespace",
        "pool",
        "rgw-user",
        "snapshot",
    )
)

_COMPONENT = re.compile(r"saltext-ci-[A-Za-z0-9][A-Za-z0-9_.-]{0,243}")
_DAEMON = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,511}")
_OWNER_APPLICATIONS = frozenset(("saltext_ci_owned", "saltext_ci_updated"))
_POOL_EXPECTED_OPTIONS = {
    "pg_num": 8,
    "size": 3,
    "min_size": 2,
    "pg_autoscale_mode": "off",
}
_MIB = 1024 * 1024


class StoragePolicyError(ValueError):
    """A storage capability or write is outside the live-test boundary."""


def _component(value):
    return isinstance(value, str) and _COMPONENT.fullmatch(value) is not None


def _parts(value, separator, count):
    if not isinstance(value, str):
        return None
    values = value.split(separator)
    if len(values) != count or not all(_component(item) for item in values):
        return None
    return tuple(values)


def validate_resource(kind, identifier):
    """Validate one canonical storage resource identifier."""
    if kind not in STORAGE_KINDS:
        raise StoragePolicyError("Unsupported storage capability type.")
    valid = False
    if kind in ("pool", "fs", "rgw-user", "bucket"):
        valid = _component(identifier)
    elif kind in ("namespace", "image"):
        valid = _parts(identifier, "/", 2) is not None
    elif kind == "snapshot":
        image, marker, snapshot = identifier.partition("@")
        valid = bool(marker) and _parts(image, "/", 2) is not None and _component(snapshot)
    elif kind in ("cephfs-group", "cephfs-subvolume"):
        valid = _parts(identifier, "/", 2 if kind == "cephfs-group" else 3) is not None
    elif kind == "cephfs-snapshot":
        subvolume, marker, snapshot = identifier.partition("@")
        valid = bool(marker) and _parts(subvolume, "/", 3) is not None and _component(snapshot)
    if not valid:
        raise StoragePolicyError(
            "Storage capabilities require exact saltext-ci-* resource identities."
        )
    return kind, identifier


def _exact(value, keys):
    return isinstance(value, Mapping) and set(value) == set(keys)


def _bounded_positive(value, maximum):
    return not isinstance(value, bool) and isinstance(value, int) and 0 < value <= maximum


class StorageWritePolicy:
    """Authorize only the storage calls emitted by the destructive test matrix."""

    def __init__(self, leased):
        self._leased = frozenset(leased or ())

    def _has(self, kind, identifier):
        return f"{kind}:{identifier}" in self._leased

    def _require(self, kind, identifier):
        if not self._has(kind, identifier):
            raise StoragePolicyError("Storage write exceeds its active resource lease.")

    def _rgw_daemon(self, daemon_name):
        """Bind a Dashboard daemon selector to one exact leased RGW service."""
        if not isinstance(daemon_name, str) or _DAEMON.fullmatch(daemon_name) is None:
            return False
        matches = []
        for resource in self._leased:
            if not resource.startswith("service:rgw."):
                continue
            service_name = resource.removeprefix("service:")
            service_id = service_name.removeprefix("rgw.")
            if any(
                daemon_name == prefix or daemon_name.startswith(f"{prefix}.")
                for prefix in (service_id, service_name)
            ):
                matches.append(service_name)
        if len(matches) != 1:
            return False
        self._require("service", matches[0])
        return True

    @staticmethod
    def _unquoted_item(path, prefix):
        if not path.startswith(prefix):
            return None
        encoded = path[len(prefix) :]
        if not encoded or "/" in encoded:
            return None
        # Test identities contain only URL-safe characters; rejecting percent
        # escapes here prevents alternate spellings of the same capability.
        return encoded if "%" not in encoded else None

    def _pool(self, method, path, params, data):
        if method == "POST" and path == "/api/pool":
            if not _exact(
                data,
                (
                    "pool",
                    "pg_num",
                    "pool_type",
                    "application_metadata",
                    "size",
                    "min_size",
                    "pg_autoscale_mode",
                ),
            ):
                return False
            pool = data["pool"]
            self._require("pool", pool)
            applications = data["application_metadata"]
            return (
                params is None
                and data["pg_num"] == 8
                and data["pool_type"] == "replicated"
                and data["size"] == 3
                and data["min_size"] == 2
                and data["pg_autoscale_mode"] == "off"
                and isinstance(applications, list)
                and len(applications) == len(set(applications))
                and set(applications).intersection(("rbd", "cephfs"))
                and set(applications).intersection(_OWNER_APPLICATIONS)
                and set(applications).issubset({"rbd", "cephfs", *_OWNER_APPLICATIONS})
            )
        pool = self._unquoted_item(path, "/api/pool/")
        if pool is None or not _component(pool):
            return False
        self._require("pool", pool)
        if method == "PUT":
            if params is not None or not isinstance(data, Mapping) or not data:
                return False
            if _exact(data, ("application_metadata",)):
                return isinstance(data["application_metadata"], list) and set(
                    data["application_metadata"]
                ) in (
                    {"rbd", "saltext_ci_owned", "saltext_ci_updated"},
                    {"cephfs", "saltext_ci_owned", "saltext_ci_updated"},
                )
            return set(data).issubset(_POOL_EXPECTED_OPTIONS) and all(
                data[key] == _POOL_EXPECTED_OPTIONS[key] for key in data
            )
        return method == "DELETE" and params is None and data is None

    def _namespace(self, method, path, params, data):
        prefix = "/api/block/pool/"
        if not path.startswith(prefix):
            return False
        remainder = path[len(prefix) :]
        parts = remainder.split("/")
        if len(parts) not in (2, 3) or parts[1] != "namespace":
            return False
        pool = parts[0]
        if not _component(pool):
            return False
        self._require("pool", pool)
        if method == "POST" and len(parts) == 2:
            if params is not None or not _exact(data, ("namespace",)):
                return False
            namespace = data["namespace"]
            self._require("namespace", f"{pool}/{namespace}")
            return _component(namespace)
        if method == "DELETE" and len(parts) == 3:
            namespace = parts[2]
            self._require("namespace", f"{pool}/{namespace}")
            return _component(namespace) and params is None and data is None
        return False

    def _image(self, method, path, params, data):
        if method == "POST" and path == "/api/block/image":
            if params is not None or not _exact(
                data, ("name", "pool_name", "size", "features", "metadata")
            ):
                return False
            image = f"{data['pool_name']}/{data['name']}"
            self._require("pool", data["pool_name"])
            self._require("image", image)
            marker = f"saltext-ci-owner:{data['name']}"
            return (
                _component(data["pool_name"])
                and _component(data["name"])
                and _bounded_positive(data["size"], 64 * _MIB)
                and data["features"] == ["layering"]
                and data["metadata"] == {"saltext.ci.owner": marker}
            )
        prefix = "/api/block/image/"
        if not path.startswith(prefix):
            return False
        remainder = path[len(prefix) :]
        encoded_image, separator, suffix = remainder.partition("/")
        for resource in self._leased:
            if not resource.startswith("image:"):
                continue
            image = resource.removeprefix("image:")
            if encoded_image != quote(image, safe=""):
                continue
            self._require("image", image)
            pool, image_name = image.split("/", 1)
            self._require("pool", pool)
            if not separator:
                if method == "PUT":
                    marker = f"saltext-ci-owner:{image_name}:updated"
                    return params is None and data in (
                        {"metadata": {"saltext.ci.owner": marker}},
                        {"features": ["layering"]},
                    )
                return method == "DELETE" and params is None and data is None
            if suffix == "snap" and method == "POST":
                if params is not None or not _exact(data, ("snapshot_name", "mirrorImageSnapshot")):
                    return False
                snapshot = data["snapshot_name"]
                self._require("snapshot", f"{image}@{snapshot}")
                return _component(snapshot) and data["mirrorImageSnapshot"] is False
            if suffix.startswith("snap/") and method == "DELETE":
                snapshot = suffix.removeprefix("snap/")
                self._require("snapshot", f"{image}@{snapshot}")
                return _component(snapshot) and params is None and data is None
        return False

    def _filesystem(self, method, path, params, data):
        if method == "POST" and path == "/api/cephfs":
            if params is not None or not _exact(
                data, ("name", "service_spec", "data_pool", "metadata_pool")
            ):
                return False
            filesystem = data["name"]
            self._require("fs", filesystem)
            self._require("pool", data["data_pool"])
            self._require("pool", data["metadata_pool"])
            spec = data["service_spec"]
            if not _exact(spec, ("placement",)) or not _exact(spec["placement"], ("hosts",)):
                return False
            hosts = spec["placement"]["hosts"]
            if not isinstance(hosts, list) or len(hosts) != 1:
                return False
            self._require("host", hosts[0])
            return all(
                _component(value)
                for value in (filesystem, data["data_pool"], data["metadata_pool"])
            )
        prefix = "/api/cephfs/remove/"
        filesystem = self._unquoted_item(path, prefix)
        if filesystem is None:
            return False
        self._require("fs", filesystem)
        return method == "DELETE" and params is None and data is None

    def _cephfs_volume(  # pylint: disable=too-many-return-statements
        self, method, path, params, data
    ):
        group_path = "/api/cephfs/subvolume/group"
        subvolume_path = "/api/cephfs/subvolume"
        snapshot_path = "/api/cephfs/subvolume/snapshot"
        if method == "POST" and path == group_path:
            if params is not None or not _exact(data, ("vol_name", "group_name", "size")):
                return False
            resource = f"{data['vol_name']}/{data['group_name']}"
            self._require("fs", data["vol_name"])
            self._require("cephfs-group", resource)
            return _bounded_positive(data["size"], 128 * _MIB)
        if method == "POST" and path == subvolume_path:
            if params is not None or not _exact(
                data, ("vol_name", "subvol_name", "group_name", "size")
            ):
                return False
            resource = f"{data['vol_name']}/{data['group_name']}/{data['subvol_name']}"
            self._require("fs", data["vol_name"])
            self._require("cephfs-group", f"{data['vol_name']}/{data['group_name']}")
            self._require("cephfs-subvolume", resource)
            return _bounded_positive(data["size"], 64 * _MIB)
        if method == "POST" and path == snapshot_path:
            if params is not None or not _exact(
                data, ("vol_name", "subvol_name", "snap_name", "group_name")
            ):
                return False
            subvolume = f"{data['vol_name']}/{data['group_name']}/{data['subvol_name']}"
            self._require("cephfs-subvolume", subvolume)
            self._require("cephfs-snapshot", f"{subvolume}@{data['snap_name']}")
            return _component(data["snap_name"])

        for kind, base, expected_params, maximum in (
            ("cephfs-group", group_path, ("group_name",), 128 * _MIB),
            (
                "cephfs-subvolume",
                subvolume_path,
                ("subvol_name", "group_name", "retain_snapshots"),
                64 * _MIB,
            ),
        ):
            filesystem = self._unquoted_item(path, f"{base}/")
            if filesystem is None:
                continue
            self._require("fs", filesystem)
            name_key = "group_name" if kind == "cephfs-group" else "subvol_name"
            if method == "PUT":
                keys = (
                    (name_key, "size")
                    if kind == "cephfs-group"
                    else (
                        "subvol_name",
                        "size",
                        "group_name",
                    )
                )
                if params is not None or not _exact(data, keys):
                    return False
                group = data.get("group_name", data[name_key])
                identifier = f"{filesystem}/{group}"
                if kind == "cephfs-subvolume":
                    identifier = f"{identifier}/{data['subvol_name']}"
                self._require(kind, identifier)
                return _bounded_positive(data["size"], maximum)
            if method == "DELETE":
                if data is not None or not _exact(params, expected_params):
                    return False
                group = params["group_name"]
                identifier = f"{filesystem}/{group}"
                if kind == "cephfs-subvolume":
                    identifier = f"{identifier}/{params['subvol_name']}"
                    if params["retain_snapshots"] is not False:
                        return False
                self._require(kind, identifier)
                return True

        prefix = f"{snapshot_path}/"
        if method == "DELETE" and path.startswith(prefix):
            remainder = path[len(prefix) :]
            if (
                remainder.count("/") != 1
                or data is not None
                or not _exact(params, ("snap_name", "group_name", "force"))
            ):
                return False
            filesystem, subvolume_name = remainder.split("/", 1)
            subvolume = f"{filesystem}/{params['group_name']}/{subvolume_name}"
            self._require("cephfs-subvolume", subvolume)
            self._require("cephfs-snapshot", f"{subvolume}@{params['snap_name']}")
            return params["force"] is True
        return False

    def _rgw_user(self, method, path, params, data):
        if method == "POST" and path == "/api/rgw/user":
            if params is not None or not _exact(
                data,
                (
                    "uid",
                    "display_name",
                    "max_buckets",
                    "system",
                    "suspended",
                    "generate_key",
                    "daemon_name",
                ),
            ):
                return False
            uid = data["uid"]
            self._require("rgw-user", uid)
            return (
                data["display_name"] == f"saltext-ci-owner:{uid}"
                and data["max_buckets"] == 4
                and data["system"] is False
                and data["suspended"] is False
                and data["generate_key"] is True
                and self._rgw_daemon(data["daemon_name"])
            )
        uid = self._unquoted_item(path, "/api/rgw/user/")
        if uid is None:
            return False
        self._require("rgw-user", uid)
        if method == "PUT":
            if params is not None or not _exact(
                data,
                ("display_name", "max_buckets", "system", "suspended", "daemon_name"),
            ):
                return False
            return (
                data["display_name"] == f"saltext-ci-owner:{uid}:updated"
                and data["max_buckets"] == 8
                and data["system"] is False
                and data["suspended"] is False
                and self._rgw_daemon(data["daemon_name"])
            )
        return (
            method == "DELETE"
            and _exact(params, ("daemon_name",))
            and self._rgw_daemon(params["daemon_name"])
            and data is None
        )

    def _bucket(self, method, path, params, data):
        if method == "POST" and path == "/api/rgw/bucket":
            if params is not None or not _exact(
                data,
                ("bucket", "uid", "lock_enabled", "encryption_state", "daemon_name"),
            ):
                return False
            self._require("bucket", data["bucket"])
            self._require("rgw-user", data["uid"])
            return (
                data["lock_enabled"] is False
                and data["encryption_state"] is False
                and self._rgw_daemon(data["daemon_name"])
            )
        bucket = self._unquoted_item(path, "/api/rgw/bucket/")
        if bucket is None:
            return False
        self._require("bucket", bucket)
        if method == "PUT":
            if params is not None or not _exact(
                data,
                (
                    "bucket_id",
                    "uid",
                    "versioning_state",
                    "encryption_state",
                    "daemon_name",
                ),
            ):
                return False
            self._require("rgw-user", data["uid"])
            bucket_id = data["bucket_id"]
            return (
                isinstance(bucket_id, str)
                and 0 < len(bucket_id) <= 512
                and not re.search(r"[\x00-\x1f\x7f]", bucket_id)
                and data["versioning_state"] == "Enabled"
                and data["encryption_state"] is False
                and self._rgw_daemon(data["daemon_name"])
            )
        return (
            method == "DELETE"
            and _exact(params, ("daemon_name",))
            and self._rgw_daemon(params["daemon_name"])
            and data is None
        )

    def authorize(self, method, path, api_version, params, data):
        """Return true for one exact lifecycle request, otherwise fail closed."""
        if api_version != "1.0":
            return False
        checks = (
            self._pool,
            self._namespace,
            self._image,
            self._filesystem,
            self._cephfs_volume,
            self._rgw_user,
            self._bucket,
        )
        return any(check(method, path, params, data) for check in checks)
