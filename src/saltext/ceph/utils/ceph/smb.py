"""Operations from current Ceph's public ``smb.py`` controllers."""

import re
from collections.abc import Mapping
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
CLUSTER_PATH = "/api/smb/cluster"
SHARE_PATH = "/api/smb/share"
JOIN_AUTH_PATH = "/api/smb/joinauth"
USERS_GROUPS_PATH = "/api/smb/usersgroups"
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SECRET_KEYS = frozenset(("password", "passwd", "secret", "token", "private_key"))
_RESOURCE_IDS = {
    "ceph.smb.cluster": ("cluster_id",),
    "ceph.smb.share": ("cluster_id", "share_id"),
    "ceph.smb.join.auth": ("auth_id",),
    "ceph.smb.usersgroups": ("users_groups_id",),
}


def _identifier(value, label):
    return validation.identifier(value, label, pattern=_ID_PATTERN, max_length=128)


def validate_identifier(value, label="identifier"):
    """Validate one SMB resource identifier."""
    return _identifier(value, label)


def _redact(value):
    if isinstance(value, Mapping):
        result = {}
        redacted = False
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in _SECRET_KEYS:
                result[key] = "***********"
                redacted = True
            else:
                result[key], child_redacted = _redact(child)
                redacted = redacted or child_redacted
        if redacted:
            result["redacted"] = True
        return result, redacted
    if isinstance(value, list):
        result = []
        redacted = False
        for child in value:
            item, child_redacted = _redact(child)
            result.append(item)
            redacted = redacted or child_redacted
        return result, redacted
    return value, False


def _safe_response(response, label, *, list_response=False, allow_none=False):
    if response.data is None and allow_none:
        return response
    try:
        data = validation.json_value(response.data, label)
    except ConfigurationError:
        raise ProtocolError(f"{label} returned invalid JSON data.") from None
    if list_response:
        if not isinstance(data, list) or not all(isinstance(item, Mapping) for item in data):
            raise ProtocolError(f"{label} returned an unexpected response shape.")
    elif not isinstance(data, Mapping):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    data, _ = _redact(data)
    return APIResponse(response.status, data, response.headers)


def _resource(value, resource_type):
    if not isinstance(value, Mapping):
        raise ConfigurationError("resource must be a mapping.")
    result = validation.json_value(value, "resource")
    if result.get("resource_type", resource_type) != resource_type:
        raise ConfigurationError(f"resource_type must be {resource_type}.")
    result["resource_type"] = resource_type
    if result.get("intent", "present") != "present":
        raise ConfigurationError("resource intent must be present.")
    result["intent"] = "present"
    for identity in _RESOURCE_IDS[resource_type]:
        result[identity] = _identifier(result.get(identity), identity)
    return result


def _route(path, *identifiers):
    return path + "".join(
        f"/{quote(_identifier(value, 'identifier'), safe='')}" for value in identifiers
    )


def _no_inline_secrets(value):
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in _SECRET_KEYS:
                raise ConfigurationError(
                    "Secret SMB fields must be supplied through a secret file."
                )
            _no_inline_secrets(child)
    elif isinstance(value, list):
        for child in value:
            _no_inline_secrets(child)


def normalize_cluster_resource(value):
    """Validate and detach an SMB cluster resource for state comparison."""
    result = _resource(value, "ceph.smb.cluster")
    _no_inline_secrets(result)
    if result.get("auth_mode") not in ("active-directory", "user"):
        raise ConfigurationError("SMB cluster auth_mode must be active-directory or user.")
    return result


def normalize_share_resource(value):
    """Validate and detach an SMB share resource for state comparison."""
    result = _resource(value, "ceph.smb.share")
    _no_inline_secrets(result)
    cephfs = result.get("cephfs")
    if not isinstance(cephfs, Mapping) or not isinstance(cephfs.get("volume"), str):
        raise ConfigurationError("SMB share resource requires a CephFS volume.")
    return result


def normalize_qos_limits(limits):
    """Validate and detach explicitly managed SMB share QoS limits."""
    allowed = {
        "read_iops_limit": 1_000_000,
        "write_iops_limit": 1_000_000,
        "read_bw_limit": None,
        "write_bw_limit": None,
        "read_delay_max": 300,
        "write_delay_max": 300,
    }
    if not isinstance(limits, Mapping) or not limits or set(limits) - set(allowed):
        raise ConfigurationError("Provide at least one supported SMB QoS limit.")
    result = {}
    for key, value in limits.items():
        value = validation.non_negative_integer(value, key)
        if allowed[key] is not None and value > allowed[key]:
            raise ConfigurationError(f"{key} exceeds its supported maximum.")
        result[key] = value
    return result


def list_clusters(client):
    """List SMB clusters."""
    response = client.request("GET", CLUSTER_PATH, api_version=API_VERSION)
    return _safe_response(response, "Ceph SMB cluster list", list_response=True)


def get_cluster(client, cluster_id):
    """Return one SMB cluster."""
    response = client.request("GET", _route(CLUSTER_PATH, cluster_id), api_version=API_VERSION)
    return _safe_response(response, "Ceph SMB cluster")


def create_cluster(client, resource):
    """Create an SMB cluster from a cluster resource."""
    resource = normalize_cluster_resource(resource)
    response = client.request(
        "POST", CLUSTER_PATH, api_version=API_VERSION, data={"cluster_resource": resource}
    )
    return _safe_response(response, "Ceph SMB cluster creation")


def delete_cluster(client, cluster_id, confirm=False):
    """Delete an SMB cluster after explicit confirmation."""
    if confirm is not True:
        raise ConfigurationError("Deleting an SMB cluster requires confirm=True.")
    response = client.request("DELETE", _route(CLUSTER_PATH, cluster_id), api_version=API_VERSION)
    return _safe_response(response, "Ceph SMB cluster deletion", allow_none=True)


def list_shares(client, cluster_id=None):
    """List SMB shares, optionally for one cluster."""
    params = {}
    if cluster_id is not None:
        params["cluster_id"] = _identifier(cluster_id, "cluster_id")
    response = client.request("GET", SHARE_PATH, api_version=API_VERSION, params=params)
    return _safe_response(response, "Ceph SMB share list", list_response=True)


def get_share(client, cluster_id, share_id):
    """Return one SMB share."""
    response = client.request(
        "GET", _route(SHARE_PATH, cluster_id, share_id), api_version=API_VERSION
    )
    return _safe_response(response, "Ceph SMB share")


def create_share(client, resource):
    """Create an SMB share from a share resource."""
    resource = normalize_share_resource(resource)
    response = client.request(
        "POST", SHARE_PATH, api_version=API_VERSION, data={"share_resource": resource}
    )
    return _safe_response(response, "Ceph SMB share creation")


def update_share_qos(client, cluster_id, share_id, **limits):
    """Update explicitly supplied QoS limits for an SMB share."""
    limits = normalize_qos_limits(limits)
    data = {
        "cluster_id": _identifier(cluster_id, "cluster_id"),
        "share_id": _identifier(share_id, "share_id"),
    }
    data.update(limits)
    response = client.request("PUT", f"{SHARE_PATH}/qos", api_version=API_VERSION, data=data)
    return _safe_response(response, "Ceph SMB share QoS update")


def delete_share(client, cluster_id, share_id, confirm=False):
    """Delete an SMB share after explicit confirmation."""
    if confirm is not True:
        raise ConfigurationError("Deleting an SMB share requires confirm=True.")
    response = client.request(
        "DELETE", _route(SHARE_PATH, cluster_id, share_id), api_version=API_VERSION
    )
    return _safe_response(response, "Ceph SMB share deletion", allow_none=True)


def list_join_auths(client):
    """List SMB join-auth resources."""
    response = client.request("GET", JOIN_AUTH_PATH, api_version=API_VERSION)
    return _safe_response(response, "Ceph SMB join-auth list", list_response=True)


def get_join_auth(client, auth_id):
    """Return one SMB join-auth resource."""
    response = client.request("GET", _route(JOIN_AUTH_PATH, auth_id), api_version=API_VERSION)
    return _safe_response(response, "Ceph SMB join auth")


def create_join_auth(client, auth_id, username, password, linked_to_cluster=None):
    """Create an SMB join-auth resource from domain credentials."""
    if not isinstance(username, str) or not username or re.search(r"[\x00-\x1f\x7f]", username):
        raise ConfigurationError("username must be non-empty text without controls.")
    if not isinstance(password, str) or not password or "\x00" in password:
        raise ConfigurationError("password must be non-empty text without NUL bytes.")
    resource = {
        "resource_type": "ceph.smb.join.auth",
        "auth_id": _identifier(auth_id, "auth_id"),
        "intent": "present",
        "auth": {"username": username, "password": password},
    }
    if linked_to_cluster is not None:
        resource["linked_to_cluster"] = _identifier(linked_to_cluster, "linked_to_cluster")
    response = client.request(
        "POST", JOIN_AUTH_PATH, api_version=API_VERSION, data={"join_auth": resource}
    )
    return _safe_response(response, "Ceph SMB join-auth creation")


def delete_join_auth(client, auth_id, confirm=False):
    """Delete an SMB join-auth resource after explicit confirmation."""
    if confirm is not True:
        raise ConfigurationError("Deleting SMB join auth requires confirm=True.")
    response = client.request("DELETE", _route(JOIN_AUTH_PATH, auth_id), api_version=API_VERSION)
    return _safe_response(response, "Ceph SMB join-auth deletion", allow_none=True)


def list_usersgroups(client):
    """List SMB users/groups resources."""
    response = client.request("GET", USERS_GROUPS_PATH, api_version=API_VERSION)
    return _safe_response(response, "Ceph SMB users/groups list", list_response=True)


def get_usersgroups(client, users_groups_id):
    """Return one SMB users/groups resource."""
    response = client.request(
        "GET", _route(USERS_GROUPS_PATH, users_groups_id), api_version=API_VERSION
    )
    return _safe_response(response, "Ceph SMB users/groups")


def create_usersgroups(client, users_groups_id, values, linked_to_cluster=None):
    """Create an SMB users/groups resource."""
    if not isinstance(values, Mapping) or set(values) != {"users", "groups"}:
        raise ConfigurationError("values must contain users and groups.")
    values = validation.json_value(values, "values")
    if not isinstance(values["users"], list) or not isinstance(values["groups"], list):
        raise ConfigurationError("values users and groups must be lists.")
    for user in values["users"]:
        if not isinstance(user, Mapping) or set(user) != {"name", "password"}:
            raise ConfigurationError("Each SMB user must contain name and password.")
        if not all(isinstance(user[key], str) and user[key] for key in ("name", "password")):
            raise ConfigurationError("SMB user names and passwords must be non-empty strings.")
    for group in values["groups"]:
        if (
            not isinstance(group, Mapping)
            or set(group) != {"name"}
            or not isinstance(group["name"], str)
        ):
            raise ConfigurationError("Each SMB group must contain a string name.")
    resource = {
        "resource_type": "ceph.smb.usersgroups",
        "users_groups_id": _identifier(users_groups_id, "users_groups_id"),
        "intent": "present",
        "values": values,
    }
    if linked_to_cluster is not None:
        resource["linked_to_cluster"] = _identifier(linked_to_cluster, "linked_to_cluster")
    response = client.request(
        "POST", USERS_GROUPS_PATH, api_version=API_VERSION, data={"usersgroups": resource}
    )
    return _safe_response(response, "Ceph SMB users/groups creation")


def delete_usersgroups(client, users_groups_id, confirm=False):
    """Delete an SMB users/groups resource after explicit confirmation."""
    if confirm is not True:
        raise ConfigurationError("Deleting SMB users/groups requires confirm=True.")
    response = client.request(
        "DELETE", _route(USERS_GROUPS_PATH, users_groups_id), api_version=API_VERSION
    )
    return _safe_response(response, "Ceph SMB users/groups deletion", allow_none=True)
