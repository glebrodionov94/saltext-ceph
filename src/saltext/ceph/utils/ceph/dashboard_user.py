"""Operations from Dashboard's public login-user ``user.py`` controller."""

import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/user"
_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@+-]{0,254}")
_ROLE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@+/-]{0,254}")
_SENSITIVE_FIELDS = frozenset(("password", "old_password", "new_password", "token"))


def validate_username(value):
    """Validate a bounded Dashboard login name."""
    if not isinstance(value, str) or not _USERNAME_PATTERN.fullmatch(value):
        raise ConfigurationError("username contains unsupported characters.")
    return value


def _optional_text(value, label, max_length=4096):
    if value is not None and (
        not isinstance(value, str) or len(value) > max_length or "\x00" in value
    ):
        raise ConfigurationError(f"{label} must be a bounded string or None.")
    return value


def validate_password(value, optional=False):
    """Validate password transport shape without exposing its contents."""
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ConfigurationError("password must be a non-empty string without NUL bytes.")
    return value


def validate_roles(value):
    """Validate an optional, duplicate-free list of Dashboard role names."""
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError("roles must be a list.")
    roles = list(value)
    if any(not isinstance(role, str) or not _ROLE_PATTERN.fullmatch(role) for role in roles):
        raise ConfigurationError("roles contains an unsupported role name.")
    if len(set(roles)) != len(roles):
        raise ConfigurationError("roles must not contain duplicates.")
    return roles


def _expiration(value):
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise ConfigurationError("pwd_expiration_date must be a non-negative Unix timestamp.")
    return value


def _boolean(value, label, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _safe_user(data):
    if not isinstance(data, Mapping):
        raise ProtocolError("Ceph Dashboard user returned an unexpected response shape.")
    return {
        key: value
        for key, value in data.items()
        if not isinstance(key, str) or key.lower() not in _SENSITIVE_FIELDS
    }


def _user_response(response):
    return APIResponse(response.status, _safe_user(response.data), response.headers)


def list_(client):
    """List Dashboard login users without password material."""
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    if not isinstance(response.data, list):
        raise ProtocolError("Ceph Dashboard user list returned an unexpected response shape.")
    return APIResponse(
        response.status, [_safe_user(item) for item in response.data], response.headers
    )


def get(client, username):
    """Return one Dashboard login user without password material."""
    username = validate_username(username)
    response = client.request(
        "GET", f"{RESOURCE_PATH}/{quote(username, safe='')}", api_version=API_VERSION
    )
    return _user_response(response)


def create(
    client,
    username,
    password=None,
    name=None,
    email=None,
    roles=None,
    enabled=True,
    pwd_expiration_date=None,
    pwd_update_required=True,
):
    """Create a Dashboard login user and discard any echoed password field."""
    data = {
        "username": validate_username(username),
        "password": validate_password(password, optional=True),
        "name": _optional_text(name, "name"),
        "email": _optional_text(email, "email"),
        "roles": validate_roles(roles),
        "enabled": _boolean(enabled, "enabled"),
        "pwdExpirationDate": _expiration(pwd_expiration_date),
        "pwdUpdateRequired": _boolean(pwd_update_required, "pwd_update_required"),
    }
    response = client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)
    return _user_response(response)


def update(
    client,
    username,
    password=None,
    name=None,
    email=None,
    roles=None,
    enabled=None,
    pwd_expiration_date=None,
    pwd_update_required=False,
):
    """Replace the mutable fields of a Dashboard login user."""
    username = validate_username(username)
    data = {
        "password": validate_password(password, optional=True),
        "name": _optional_text(name, "name"),
        "email": _optional_text(email, "email"),
        "roles": validate_roles(roles),
        "enabled": _boolean(enabled, "enabled", optional=True),
        "pwdExpirationDate": _expiration(pwd_expiration_date),
        "pwdUpdateRequired": _boolean(pwd_update_required, "pwd_update_required"),
    }
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/{quote(username, safe='')}",
        api_version=API_VERSION,
        data=data,
    )
    return _user_response(response)


def delete(client, username, confirm=False):
    """Delete a Dashboard login user after explicit confirmation."""
    validation.confirmation(confirm, "Deleting a Dashboard user")
    username = validate_username(username)
    response = client.request(
        "DELETE", f"{RESOURCE_PATH}/{quote(username, safe='')}", api_version=API_VERSION
    )
    return APIResponse(response.status, {"username": username}, response.headers)


def validate_password_policy(client, password, username=None, old_password=None):
    """Ask Dashboard to evaluate a password and return only policy metadata."""
    data = {
        "password": validate_password(password),
        "username": validate_username(username) if username is not None else None,
        "old_password": validate_password(old_password, optional=True),
    }
    response = client.request(
        "POST", f"{RESOURCE_PATH}/validate_password", api_version=API_VERSION, data=data
    )
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph password validation returned an unexpected response shape.")
    valid = response.data.get("valid")
    credits_value = response.data.get("credits")
    valuation = response.data.get("valuation")
    if (
        not isinstance(valid, bool)
        or isinstance(credits_value, bool)
        or not isinstance(credits_value, int)
        or not isinstance(valuation, (str, type(None)))
    ):
        raise ProtocolError("Ceph password validation returned an unexpected response shape.")
    result = {"valid": valid, "credits": credits_value, "valuation": valuation}
    return APIResponse(response.status, result, response.headers)


def change_password(client, username, old_password, new_password):
    """Change the authenticated user's password without returning either secret."""
    username = validate_username(username)
    data = {
        "old_password": validate_password(old_password),
        "new_password": validate_password(new_password),
    }
    response = client.request(
        "POST",
        f"{RESOURCE_PATH}/{quote(username, safe='')}/change_password",
        api_version=API_VERSION,
        data=data,
    )
    return APIResponse(response.status, {"username": username}, response.headers)
