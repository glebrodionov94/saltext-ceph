"""Operations from Dashboard's public ``nfs.py`` controllers."""

import posixpath
import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

CLUSTER_API_VERSION = "0.1"
READ_API_VERSION = "1.0"
MUTATION_API_VERSION = "2.0"
CLUSTER_PATH = "/api/nfs-ganesha/cluster"
EXPORT_PATH = "/api/nfs-ganesha/export"

_ACCESS_TYPES = frozenset(("RW", "RO", "NONE"))
_SQUASH_POLICIES = frozenset(
    (
        "root",
        "root_squash",
        "rootsquash",
        "rootid",
        "root_id_squash",
        "rootidsquash",
        "all",
        "all_squash",
        "allsquash",
        "all_anomnymous",
        "allanonymous",
        "no_root_squash",
        "none",
        "noidsquash",
    )
)
_TRANSPORTS = frozenset(("TCP", "UDP", "RDMA"))
_FSALS = frozenset(("CEPH", "RGW"))
_RGW_USER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@$-]*")
_XATTR_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*")


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _bounded_text(value, label, *, max_length=4096):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError(f"{label} must be a non-empty bounded text value.")
    return value


def _cluster_id(value):
    return validation.identifier(value, "cluster_id")


def _export_id(value):
    value = validation.non_negative_integer(value, "export_id")
    if value == 0:
        raise ConfigurationError("export_id must be a positive integer.")
    return value


def _canonical_absolute_path(value, label, *, allow_root):
    value = _bounded_text(value, label)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or re.search(r"[><|&()]", value)
        or posixpath.normpath(value) != value
        or (not allow_root and value == "/")
    ):
        suffix = "" if allow_root else " other than '/'."
        raise ConfigurationError(f"{label} must be a canonical absolute POSIX path{suffix}")
    return value


def _access_type(value, label="access_type"):
    if not isinstance(value, str) or value.upper() not in _ACCESS_TYPES:
        raise ConfigurationError(f"{label} must be RW, RO, or NONE.")
    return value.upper()


def _squash(value, label="squash"):
    if not isinstance(value, str) or value.lower() not in _SQUASH_POLICIES:
        raise ConfigurationError(f"{label} is not a supported NFS squash policy.")
    return value.lower()


def _protocols(values):
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError("protocols must be a non-empty list.")
    result = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value not in (3, 4):
            raise ConfigurationError("protocols may contain only 3 and 4.")
        result.append(value)
    if len(set(result)) != len(result):
        raise ConfigurationError("protocols must not contain duplicates.")
    return result


def _transports(values):
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError("transports must be a non-empty list.")
    result = []
    for value in values:
        if not isinstance(value, str) or value.upper() not in _TRANSPORTS:
            raise ConfigurationError("transports may contain only TCP, UDP, and RDMA.")
        result.append(value.upper())
    if len(set(result)) != len(result):
        raise ConfigurationError("transports must not contain duplicates.")
    return result


def _fsal(value, path):
    if not isinstance(value, Mapping):
        raise ConfigurationError("fsal must be a mapping.")
    unknown = set(value) - {"name", "fs_name", "sec_label_xattr", "user_id"}
    if unknown:
        raise ConfigurationError("fsal contains unsupported fields.")
    name = value.get("name")
    if not isinstance(name, str) or name.upper() not in _FSALS:
        raise ConfigurationError("fsal name must be CEPH or RGW.")
    name = name.upper()
    result = {"name": name}

    if name == "CEPH":
        if value.get("user_id") not in (None, ""):
            raise ConfigurationError("CephFS fsal user_id is managed by Ceph.")
        result["fs_name"] = validation.identifier(value.get("fs_name"), "fsal fs_name")
        sec_label_xattr = value.get("sec_label_xattr")
        if sec_label_xattr is not None:
            result["sec_label_xattr"] = validation.identifier(
                sec_label_xattr,
                "fsal sec_label_xattr",
                pattern=_XATTR_PATTERN,
            )
        _canonical_absolute_path(path, "path", allow_root=True)
        return result

    if value.get("fs_name") not in (None, "") or value.get("sec_label_xattr") not in (
        None,
        "",
    ):
        raise ConfigurationError("RGW fsal does not accept CephFS fields.")
    if path != "/" and "/" in path:
        raise ConfigurationError("RGW path must be '/' or a bucket name without '/'.")
    user_id = value.get("user_id")
    if path == "/" and not user_id:
        raise ConfigurationError("RGW user exports with path '/' require fsal user_id.")
    if user_id is not None:
        result["user_id"] = validation.identifier(
            user_id,
            "fsal user_id",
            pattern=_RGW_USER_PATTERN,
        )
    return result


def _address(value):
    value = _bounded_text(value, "client address", max_length=255)
    if re.search(r"\s|,", value):
        raise ConfigurationError("client addresses must be individual address expressions.")
    return value


def _clients(values):
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ConfigurationError("clients must be a list.")
    result = []
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {
            "addresses",
            "access_type",
            "squash",
        }:
            raise ConfigurationError(
                f"clients[{index}] must contain addresses, access_type, and squash."
            )
        addresses = value["addresses"]
        if (
            isinstance(addresses, (str, bytes))
            or not isinstance(addresses, Sequence)
            or not addresses
        ):
            raise ConfigurationError(f"clients[{index}] addresses must be a non-empty list.")
        addresses = [_address(address) for address in addresses]
        if len(set(addresses)) != len(addresses):
            raise ConfigurationError(f"clients[{index}] addresses must not contain duplicates.")
        result.append(
            {
                "addresses": addresses,
                "access_type": _access_type(value["access_type"], f"clients[{index}] access_type"),
                "squash": _squash(value["squash"], f"clients[{index}] squash"),
            }
        )
    return result


def _export_data(
    path,
    pseudo,
    access_type,
    squash,
    security_label,
    protocols,
    transports,
    fsal,
    clients,
):
    path = _bounded_text(path, "path")
    pseudo = _canonical_absolute_path(pseudo, "pseudo", allow_root=False)
    _boolean(security_label, "security_label")
    normalized_fsal = _fsal(fsal, path)
    if (
        security_label
        and normalized_fsal["name"] == "CEPH"
        and not normalized_fsal.get("sec_label_xattr")
    ):
        raise ConfigurationError("security_label=True requires fsal sec_label_xattr for CephFS.")
    return {
        "path": path,
        "pseudo": pseudo,
        "access_type": _access_type(access_type),
        "squash": _squash(squash),
        "security_label": security_label,
        "protocols": _protocols(protocols),
        "transports": _transports(transports),
        "fsal": normalized_fsal,
        "clients": _clients(clients),
    }


def validate_cluster_id(value):
    """Validate one NFS-Ganesha cluster identifier."""
    return _cluster_id(value)


def validate_export_id(value):
    """Validate one positive server-assigned export identifier."""
    return _export_id(value)


def validate_pseudo(value):
    """Validate one canonical non-root NFS pseudo path."""
    return _canonical_absolute_path(value, "pseudo", allow_root=False)


def normalize_export(
    path,
    cluster_id,
    pseudo,
    access_type,
    squash,
    security_label,
    protocols,
    transports,
    fsal,
    clients,
):
    """Validate and detach the public fields of an NFS export."""
    result = _export_data(
        path,
        pseudo,
        access_type,
        squash,
        security_label,
        protocols,
        transports,
        fsal,
        clients,
    )
    result["cluster_id"] = _cluster_id(cluster_id)
    return result


def clusters(client, info=False):
    """List NFS cluster names or, on current Ceph, cluster information."""
    _boolean(info, "info")
    kwargs = {"params": {"info": True}} if info else {}
    response = client.request("GET", CLUSTER_PATH, api_version=CLUSTER_API_VERSION, **kwargs)
    if info:
        return validation.mapping_list_response(response, "Ceph NFS cluster information")
    if not isinstance(response.data, list) or not all(
        isinstance(item, str) and item for item in response.data
    ):
        raise ProtocolError("Ceph NFS cluster list returned an unexpected response shape.")
    return APIResponse(response.status, list(response.data), response.headers)


def list_exports(client, cluster_id=None):
    """List every NFS export, optionally filtered on current Ceph releases."""
    kwargs = {}
    if cluster_id is not None:
        kwargs["params"] = {"cluster_id": _cluster_id(cluster_id)}
    response = client.request("GET", EXPORT_PATH, api_version=READ_API_VERSION, **kwargs)
    return validation.mapping_list_response(response, "Ceph NFS export list")


def get_export(client, cluster_id, export_id):
    """Return one NFS export, or ``None`` when the controller reports no match."""
    path = f"{EXPORT_PATH}/{quote(_cluster_id(cluster_id), safe='')}/{_export_id(export_id)}"
    response = client.request("GET", path, api_version=READ_API_VERSION)
    if response.data is None:
        return APIResponse(response.status, None, response.headers)
    return validation.mapping_response(response, "Ceph NFS export")


def create_export(
    client,
    path,
    cluster_id,
    pseudo,
    access_type,
    squash,
    security_label,
    protocols,
    transports,
    fsal,
    clients,
):
    """Create an NFS export through the version 2 controller contract."""
    data = normalize_export(
        path,
        cluster_id,
        pseudo,
        access_type,
        squash,
        security_label,
        protocols,
        transports,
        fsal,
        clients,
    )
    return client.request("POST", EXPORT_PATH, api_version=MUTATION_API_VERSION, data=data)


def update_export(
    client,
    cluster_id,
    export_id,
    path,
    pseudo,
    access_type,
    squash,
    security_label,
    protocols,
    transports,
    fsal,
    clients,
):
    """Replace the public configuration of an existing NFS export."""
    route = f"{EXPORT_PATH}/{quote(_cluster_id(cluster_id), safe='')}/{_export_id(export_id)}"
    data = _export_data(
        path,
        pseudo,
        access_type,
        squash,
        security_label,
        protocols,
        transports,
        fsal,
        clients,
    )
    return client.request("PUT", route, api_version=MUTATION_API_VERSION, data=data)


def delete_export(client, cluster_id, export_id, confirm=False):
    """Remove an NFS export after explicit confirmation; backing data remains."""
    _boolean(confirm, "confirm")
    if not confirm:
        raise ConfigurationError("Deleting an NFS export requires confirm=True.")
    route = f"{EXPORT_PATH}/{quote(_cluster_id(cluster_id), safe='')}/{_export_id(export_id)}"
    return client.request("DELETE", route, api_version=MUTATION_API_VERSION)
