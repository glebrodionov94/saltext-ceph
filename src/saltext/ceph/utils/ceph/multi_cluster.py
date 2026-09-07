"""Current-only public Dashboard multi-cluster controller operations."""

import re
from collections.abc import Mapping
from copy import deepcopy
from urllib.parse import quote
from urllib.parse import unquote
from urllib.parse import urlsplit

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.config import validate_path
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/multi-cluster"
REDACTED = "***********"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_PARTS = ("password", "token", "secret", "private_key", "access_key")


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _text(value, label, *, max_length=4096):
    if not isinstance(value, str) or not value or _CONTROL.search(value):
        raise ConfigurationError(f"{label} must be non-empty bounded text.")
    try:
        encoded_length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ConfigurationError(f"{label} must be non-empty bounded text.") from None
    if encoded_length > max_length:
        raise ConfigurationError(f"{label} must be non-empty bounded text.")
    return value


def _certificate(value):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ConfigurationError("ssl_certificate must be bounded non-empty text.")
    try:
        encoded_length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ConfigurationError("ssl_certificate must be bounded non-empty text.") from None
    if encoded_length > 1024 * 1024:
        raise ConfigurationError("ssl_certificate must be bounded non-empty text.")
    return value


def _url(value, label, *, allow_http=False):
    _boolean(allow_http, "allow_http")
    value = _text(value, label, max_length=8192)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ConfigurationError(f"{label} is not a valid Dashboard URL.") from None
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise ConfigurationError(f"{label} is not an allowed Dashboard URL.")
    if parsed.scheme == "http" and not allow_http:
        raise ConfigurationError(f"{label} is not an allowed Dashboard URL.")
    validate_path(parsed.path or "/")
    if unquote(parsed.path).rstrip("/").endswith("/api"):
        raise ConfigurationError(f"{label} must be a Dashboard root without /api.")
    return value.rstrip("/")


def _tls(ssl_verify, ssl_certificate):
    ssl_verify = _boolean(ssl_verify, "ssl_verify")
    if ssl_certificate is not None:
        ssl_certificate = _certificate(ssl_certificate)
    if ssl_verify and ssl_certificate is None:
        raise ConfigurationError("ssl_certificate is required when ssl_verify=True.")
    if not ssl_verify and ssl_certificate is not None:
        raise ConfigurationError("ssl_certificate requires ssl_verify=True.")
    return ssl_verify, ssl_certificate


def _ttl(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError("ttl must be a positive integer number of hours or None.")
    return value


def _segment(value, label):
    return quote(_text(value, label), safe="")


def _redact(value):
    changed = False
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            normalized = key.casefold().replace("-", "_") if isinstance(key, str) else ""
            if any(part in normalized for part in _SECRET_PARTS):
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


def _response(response, label, *, include_secrets=False, shape="any"):
    _boolean(include_secrets, "include_secrets")
    if shape == "mapping" and not isinstance(response.data, Mapping):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    try:
        data = validation.json_value(response.data, label)
    except ConfigurationError:
        raise ProtocolError(f"{label} returned an unexpected response shape.") from None
    if include_secrets:
        return APIResponse(response.status, data, response.headers)
    data, changed = _redact(data)
    if changed and isinstance(data, dict):
        data["redacted"] = True
    return APIResponse(response.status, data, response.headers)


def connect(
    client,
    url,
    cluster_alias,
    username,
    password,
    hub_url,
    ssl_verify=None,
    ssl_certificate=None,
    ttl=None,
    allow_http=False,
):
    """Authenticate and register a remote cluster without returning credentials."""
    ssl_verify, ssl_certificate = _tls(ssl_verify, ssl_certificate)
    data = {
        "url": _url(url, "url", allow_http=allow_http),
        "cluster_alias": _text(cluster_alias, "cluster_alias"),
        "username": _text(username, "username"),
        "password": _text(password, "password", max_length=65536),
        "hub_url": _url(hub_url, "hub_url", allow_http=allow_http),
        "ssl_verify": ssl_verify,
        "ssl_certificate": ssl_certificate,
        "ttl": _ttl(ttl),
    }
    response = client.request("POST", f"{RESOURCE_PATH}/auth", api_version=API_VERSION, data=data)
    return _response(response, "Ceph multi-cluster connection")


def set_current(client, url, username, allow_http=False):
    """Select one already configured remote cluster and user."""
    data = {
        "config": {
            "url": _url(url, "url", allow_http=allow_http),
            "user": _text(username, "username"),
        }
    }
    response = client.request(
        "PUT", f"{RESOURCE_PATH}/set_config", api_version=API_VERSION, data=data
    )
    return _response(response, "Ceph multi-cluster selection", shape="mapping")


def reconnect(
    client,
    url,
    username,
    password=None,
    cluster_token=None,
    ssl_verify=None,
    ssl_certificate=None,
    ttl=None,
    allow_http=False,
):
    """Refresh a remote connection using exactly one credential."""
    if (password is None) == (cluster_token is None):
        raise ConfigurationError("Provide exactly one of password or cluster_token.")
    ssl_verify, ssl_certificate = _tls(ssl_verify, ssl_certificate)
    data = {
        "url": _url(url, "url", allow_http=allow_http),
        "username": _text(username, "username"),
        "password": (
            _text(password, "password", max_length=65536) if password is not None else None
        ),
        "cluster_token": (
            _text(cluster_token, "cluster_token", max_length=65536)
            if cluster_token is not None
            else None
        ),
        "ssl_verify": ssl_verify,
        "ssl_certificate": ssl_certificate,
        "ttl": _ttl(ttl),
    }
    response = client.request(
        "PUT", f"{RESOURCE_PATH}/reconnect_cluster", api_version=API_VERSION, data=data
    )
    return _response(response, "Ceph multi-cluster reconnect")


def edit(
    client,
    cluster_name,
    url,
    cluster_alias,
    username,
    ssl_verify=None,
    ssl_certificate=None,
    allow_http=False,
):
    """Edit the public properties of a configured remote cluster."""
    ssl_verify, ssl_certificate = _tls(ssl_verify, ssl_certificate)
    data = {
        "name": _text(cluster_name, "cluster_name"),
        "url": _url(url, "url", allow_http=allow_http),
        "cluster_alias": _text(cluster_alias, "cluster_alias"),
        "username": _text(username, "username"),
        "verify": ssl_verify,
        "ssl_certificate": ssl_certificate,
    }
    response = client.request(
        "PUT", f"{RESOURCE_PATH}/edit_cluster", api_version=API_VERSION, data=data
    )
    return _response(response, "Ceph multi-cluster edit", shape="mapping")


def delete(client, cluster_name, cluster_user, confirm=False):
    """Remove a remote cluster connection after explicit confirmation."""
    validation.confirmation(confirm, "Deleting a multi-cluster connection")
    path = (
        f"{RESOURCE_PATH}/delete_cluster/"
        f"{_segment(cluster_name, 'cluster_name')}/{_segment(cluster_user, 'cluster_user')}"
    )
    response = client.request("DELETE", path, api_version=API_VERSION)
    return _response(response, "Ceph multi-cluster deletion", shape="mapping")


def get_config(client, include_secrets=False):
    """Return multi-cluster configuration, redacting stored tokens by default."""
    response = client.request("GET", f"{RESOURCE_PATH}/get_config", api_version=API_VERSION)
    return _response(
        response,
        "Ceph multi-cluster configuration",
        include_secrets=include_secrets,
        shape="mapping",
    )


def token_status(client):
    """Return expiry status for stored remote-cluster tokens."""
    response = client.request("GET", f"{RESOURCE_PATH}/check_token_status", api_version=API_VERSION)
    return _response(response, "Ceph multi-cluster token status", shape="mapping")


def security_config(client):
    """Return local cephadm management-gateway security status."""
    response = client.request("GET", f"{RESOURCE_PATH}/security_config", api_version=API_VERSION)
    if response.data is not None and not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph multi-cluster security config returned an unexpected shape.")
    return _response(response, "Ceph multi-cluster security config")


def prometheus_api_url(client):
    """Return the URL advertised for this cluster's Prometheus API."""
    response = client.request(
        "GET", f"{RESOURCE_PATH}/get_prometheus_api_url", api_version=API_VERSION
    )
    if response.data is not None and not isinstance(response.data, str):
        raise ProtocolError("Ceph multi-cluster Prometheus URL returned an unexpected shape.")
    return _response(response, "Ceph multi-cluster Prometheus URL")
