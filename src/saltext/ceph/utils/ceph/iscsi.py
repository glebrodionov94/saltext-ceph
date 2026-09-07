"""Operations from Dashboard's public ``iscsi.py`` controllers."""

import ipaddress
import math
import re
from collections.abc import Mapping
from collections.abc import Sequence
from copy import deepcopy
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
DISCOVERY_AUTH_PATH = "/api/iscsi/discoveryauth"
TARGET_PATH = "/api/iscsi/target"

_AUTH_FIELDS = ("user", "password", "mutual_user", "mutual_password")
_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_.:@-]{8,64}")
_PASSWORD_PATTERN = re.compile(r"[A-Za-z0-9_@/-]{12,16}")
_IQN_PATTERN = re.compile(
    r"iqn\.(?:19|20)\d{2}-(?:0[1-9]|1[0-2])\."
    r"[A-Za-z]{2,63}(?:\.[A-Za-z0-9-]+)+"
    r"(?::[A-Za-z0-9.-]+)*"
)
_CONTROL_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}")
_BACKSTORE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}")
_SECRET_FIELDS = frozenset(("password", "mutual_password"))
REDACTED = "***********"


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _redact(value):
    """Detach a response and recursively replace iSCSI CHAP secrets."""
    changed = False
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if key in _SECRET_FIELDS:
                result[key] = REDACTED
                changed = True
            else:
                result[key], item_changed = _redact(item)
                changed = changed or item_changed
        return result, changed
    if isinstance(value, list):
        result = []
        for item in value:
            item, item_changed = _redact(item)
            result.append(item)
            changed = changed or item_changed
        return result, changed
    return deepcopy(value), False


def _protected_response(response, label, *, include_secrets=False, shape="any"):
    """Validate, detach, and redact an iSCSI response by default."""
    _boolean(include_secrets, "include_secrets")
    data = response.data
    if shape == "mapping" and not isinstance(data, Mapping):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    if shape == "mapping_list" and (
        not isinstance(data, list) or not all(isinstance(item, Mapping) for item in data)
    ):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    if include_secrets:
        data = deepcopy(data)
        changed = False
    else:
        data, changed = _redact(data)
    if changed and isinstance(data, dict):
        data["redacted"] = True
    return APIResponse(response.status, data, response.headers)


def _sequence(value, label, *, optional=True):
    if value is None and optional:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError(f"{label} must be a list.")
    return list(value)


def _bounded_ascii(value, label, *, max_length=255):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or not value.isascii()
        or re.search(r"[\x00-\x20\x7f]", value)
    ):
        raise ConfigurationError(f"{label} must be non-empty bounded ASCII text.")
    return value


def _iqn(value, label="target_iqn"):
    if (
        not isinstance(value, str)
        or len(value.encode("utf-8")) > 223
        or not _IQN_PATTERN.fullmatch(value)
    ):
        raise ConfigurationError(f"{label} must be a valid IQN.")
    return value


def _auth(value, label="auth"):
    if value is None:
        value = {}
    if not isinstance(value, Mapping) or set(value) - set(_AUTH_FIELDS):
        raise ConfigurationError(f"{label} must contain only Ceph iSCSI auth fields.")
    result = {}
    for field in _AUTH_FIELDS:
        item = value.get(field, "")
        if not isinstance(item, str) or re.search(r"[\x00-\x1f\x7f]", item):
            raise ConfigurationError(f"{label} {field} must be text without controls.")
        result[field] = item

    if result["user"] or result["password"]:
        if not _USERNAME_PATTERN.fullmatch(result["user"]) or not _PASSWORD_PATTERN.fullmatch(
            result["password"]
        ):
            raise ConfigurationError(f"{label} has invalid primary CHAP credentials.")
    if result["mutual_user"] or result["mutual_password"]:
        if (
            not result["user"]
            or not _USERNAME_PATTERN.fullmatch(result["mutual_user"])
            or not _PASSWORD_PATTERN.fullmatch(result["mutual_password"])
        ):
            raise ConfigurationError(f"{label} has invalid mutual CHAP credentials.")
    return result


def _controls(value, label):
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{label} must be a mapping.")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _CONTROL_PATTERN.fullmatch(key):
            raise ConfigurationError(f"{label} contains an invalid control name.")
        if isinstance(item, float) and not math.isfinite(item):
            raise ConfigurationError(f"{label} contains a non-finite number.")
        if not isinstance(item, (str, bool, int, float)):
            raise ConfigurationError(f"{label} control values must be scalar JSON values.")
        if isinstance(item, str) and (len(item) > 255 or re.search(r"[\x00-\x1f\x7f]", item)):
            raise ConfigurationError(f"{label} contains an invalid string value.")
        result[key] = item
    return result


def _portals(values):
    values = _sequence(values, "portals", optional=False)
    if not values:
        raise ConfigurationError("portals must contain at least one gateway address.")
    result = []
    identities = set()
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {"host", "ip"}:
            raise ConfigurationError(f"portals[{index}] must contain host and ip.")
        host = validation.identifier(value["host"], f"portals[{index}] host")
        try:
            address = ipaddress.ip_address(value["ip"])
        except (TypeError, ValueError):
            raise ConfigurationError(f"portals[{index}] ip must be an IP address.") from None
        if address.is_unspecified or address.is_multicast:
            raise ConfigurationError(f"portals[{index}] ip must be a unicast address.")
        identity = (host, str(address))
        if identity in identities:
            raise ConfigurationError("portals must not contain duplicate host/address pairs.")
        identities.add(identity)
        result.append({"host": host, "ip": str(address)})
    return result


def _image_ref(value, label):
    if not isinstance(value, Mapping) or set(value) != {"pool", "image"}:
        raise ConfigurationError(f"{label} must contain pool and image.")
    return {
        "pool": validation.identifier(value["pool"], f"{label} pool"),
        "image": validation.identifier(value["image"], f"{label} image"),
    }


def _disks(values):
    values = _sequence(values, "disks")
    result = []
    identities = set()
    luns = set()
    wwns = set()
    for index, value in enumerate(values):
        required = {"pool", "image", "backstore", "controls"}
        optional = {"wwn", "lun"}
        if (
            not isinstance(value, Mapping)
            or not required.issubset(value)
            or set(value) - (required | optional)
        ):
            raise ConfigurationError(
                f"disks[{index}] requires pool, image, backstore, and controls."
            )
        image_ref = _image_ref({"pool": value["pool"], "image": value["image"]}, f"disks[{index}]")
        identity = (image_ref["pool"], image_ref["image"])
        if identity in identities:
            raise ConfigurationError("disks must not contain duplicate RBD images.")
        identities.add(identity)
        backstore = value["backstore"]
        if not isinstance(backstore, str) or not _BACKSTORE_PATTERN.fullmatch(backstore):
            raise ConfigurationError(f"disks[{index}] backstore is invalid.")
        disk = {
            **image_ref,
            "backstore": backstore,
            "controls": _controls(value["controls"], f"disks[{index}] controls"),
        }
        if value.get("lun") is not None:
            lun = validation.non_negative_integer(value["lun"], f"disks[{index}] lun")
            if lun > 16383:
                raise ConfigurationError(f"disks[{index}] lun must not exceed 16383.")
            if lun in luns:
                raise ConfigurationError("disks must not contain duplicate LUN numbers.")
            luns.add(lun)
            disk["lun"] = lun
        if value.get("wwn") is not None:
            wwn = _bounded_ascii(value["wwn"], f"disks[{index}] wwn")
            if wwn in wwns:
                raise ConfigurationError("disks must not contain duplicate WWNs.")
            wwns.add(wwn)
            disk["wwn"] = wwn
        result.append(disk)
    return result, identities


def _lun_refs(values, label, disk_identities):
    values = _sequence(values, label)
    result = []
    identities = set()
    for index, value in enumerate(values):
        image_ref = _image_ref(value, f"{label}[{index}]")
        identity = (image_ref["pool"], image_ref["image"])
        if identity not in disk_identities:
            raise ConfigurationError(f"{label}[{index}] does not reference a target disk.")
        if identity in identities:
            raise ConfigurationError(f"{label} must not contain duplicate RBD images.")
        identities.add(identity)
        result.append(image_ref)
    return result


def _clients(values, disk_identities):
    values = _sequence(values, "clients")
    result = []
    client_iqns = set()
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {"client_iqn", "luns", "auth"}:
            raise ConfigurationError(f"clients[{index}] must contain client_iqn, luns, and auth.")
        client_iqn = _iqn(value["client_iqn"], f"clients[{index}] client_iqn")
        if client_iqn in client_iqns:
            raise ConfigurationError("clients must not contain duplicate initiator IQNs.")
        client_iqns.add(client_iqn)
        result.append(
            {
                "client_iqn": client_iqn,
                "luns": _lun_refs(value["luns"], f"clients[{index}] luns", disk_identities),
                "auth": _auth(value["auth"], f"clients[{index}] auth"),
            }
        )
    return result, client_iqns


def _groups(values, disk_identities, client_iqns):
    values = _sequence(values, "groups")
    result = []
    group_ids = set()
    grouped_clients = set()
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {"group_id", "disks", "members"}:
            raise ConfigurationError(f"groups[{index}] must contain group_id, disks, and members.")
        group_id = validation.identifier(value["group_id"], f"groups[{index}] group_id")
        if group_id in group_ids:
            raise ConfigurationError("groups must not contain duplicate group IDs.")
        group_ids.add(group_id)
        members = _sequence(value["members"], f"groups[{index}] members")
        normalized_members = []
        for member_index, member in enumerate(members):
            member = _iqn(member, f"groups[{index}] members[{member_index}]")
            if member not in client_iqns:
                raise ConfigurationError(
                    f"groups[{index}] member does not reference a configured client."
                )
            if member in grouped_clients:
                raise ConfigurationError("Each client may belong to only one iSCSI group.")
            grouped_clients.add(member)
            normalized_members.append(member)
        if len(set(normalized_members)) != len(normalized_members):
            raise ConfigurationError(f"groups[{index}] members must not contain duplicates.")
        result.append(
            {
                "group_id": group_id,
                "disks": _lun_refs(value["disks"], f"groups[{index}] disks", disk_identities),
                "members": normalized_members,
            }
        )
    return result


def _target_data(
    target_iqn,
    portals,
    target_controls,
    acl_enabled,
    auth,
    disks,
    clients,
    groups,
):
    target_iqn = _iqn(target_iqn)
    normalized_disks, disk_identities = _disks(disks)
    normalized_clients, client_iqns = _clients(clients, disk_identities)
    return {
        "target_iqn": target_iqn,
        "target_controls": _controls(target_controls, "target_controls"),
        "acl_enabled": _boolean(acl_enabled, "acl_enabled"),
        "auth": _auth(auth),
        "portals": _portals(portals),
        "disks": normalized_disks,
        "clients": normalized_clients,
        "groups": _groups(groups, disk_identities, client_iqns),
    }


def _target_route(target_iqn):
    return f"{TARGET_PATH}/{quote(_iqn(target_iqn), safe='')}"


def validate_iqn(value, label="target_iqn"):
    """Validate one iSCSI qualified name."""
    return _iqn(value, label)


def normalize_target(
    target_iqn,
    portals,
    target_controls=None,
    acl_enabled=False,
    auth=None,
    disks=None,
    clients=None,
    groups=None,
):
    """Validate and detach a complete public iSCSI target configuration."""
    return _target_data(
        target_iqn,
        portals,
        target_controls,
        acl_enabled,
        auth,
        disks,
        clients,
        groups,
    )


def get_discovery_auth(client, include_secrets=False):
    """Return discovery CHAP configuration, redacting passwords by default."""
    response = client.request("GET", DISCOVERY_AUTH_PATH, api_version=API_VERSION)
    if not isinstance(response.data, Mapping) or not all(
        isinstance(response.data.get(field), str) for field in _AUTH_FIELDS
    ):
        raise ProtocolError("Ceph iSCSI discovery auth returned an unexpected response shape.")
    return _protected_response(
        response,
        "Ceph iSCSI discovery auth",
        include_secrets=include_secrets,
        shape="mapping",
    )


def set_discovery_auth(client, user="", password="", mutual_user="", mutual_password=""):
    """Set or disable iSCSI discovery CHAP credentials."""
    data = _auth(
        {
            "user": user,
            "password": password,
            "mutual_user": mutual_user,
            "mutual_password": mutual_password,
        },
        "discovery auth",
    )
    response = client.request("PUT", DISCOVERY_AUTH_PATH, api_version=API_VERSION, data=data)
    return _protected_response(response, "Ceph iSCSI discovery auth update")


def list_targets(client, include_secrets=False):
    """List all iSCSI targets with CHAP passwords redacted by default."""
    response = client.request("GET", TARGET_PATH, api_version=API_VERSION)
    return _protected_response(
        response,
        "Ceph iSCSI target list",
        include_secrets=include_secrets,
        shape="mapping_list",
    )


def get_target(client, target_iqn, include_secrets=False):
    """Return one iSCSI target with CHAP passwords redacted by default."""
    response = client.request("GET", _target_route(target_iqn), api_version=API_VERSION)
    return _protected_response(
        response,
        "Ceph iSCSI target",
        include_secrets=include_secrets,
        shape="mapping",
    )


def create_target(
    client,
    target_iqn,
    portals,
    target_controls=None,
    acl_enabled=False,
    auth=None,
    disks=None,
    clients=None,
    groups=None,
):
    """Create an iSCSI target from a complete structured configuration."""
    data = normalize_target(
        target_iqn,
        portals,
        target_controls,
        acl_enabled,
        auth,
        disks,
        clients,
        groups,
    )
    response = client.request("POST", TARGET_PATH, api_version=API_VERSION, data=data)
    return _protected_response(response, "Ceph iSCSI target creation")


def update_target(
    client,
    target_iqn,
    portals,
    new_target_iqn=None,
    target_controls=None,
    acl_enabled=False,
    auth=None,
    disks=None,
    clients=None,
    groups=None,
    confirm=False,
):
    """Replace an iSCSI target after confirming the potentially destructive edit."""
    _boolean(confirm, "confirm")
    if not confirm:
        raise ConfigurationError("Updating an iSCSI target requires confirm=True.")
    current_iqn = _iqn(target_iqn)
    data = normalize_target(
        new_target_iqn or current_iqn,
        portals,
        target_controls,
        acl_enabled,
        auth,
        disks,
        clients,
        groups,
    )
    data["new_target_iqn"] = data.pop("target_iqn")
    response = client.request("PUT", _target_route(current_iqn), api_version=API_VERSION, data=data)
    return _protected_response(response, "Ceph iSCSI target update")


def delete_target(client, target_iqn, confirm=False):
    """Delete an iSCSI target after explicit confirmation."""
    _boolean(confirm, "confirm")
    if not confirm:
        raise ConfigurationError("Deleting an iSCSI target requires confirm=True.")
    return client.request("DELETE", _target_route(target_iqn), api_version=API_VERSION)
