"""Operations from Dashboard's public ``prometheus.py`` controllers."""

import math
import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote
from urllib.parse import urlsplit

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/prometheus"
_QUERY_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}")
_METRIC_NAME = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]{0,254}")
_SILENCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}")


def _json_response(response, label, allow_none=False):
    if response.data is None and allow_none:
        return response
    try:
        data = validation.json_value(response.data, label)
    except ConfigurationError:
        raise ProtocolError(f"{label} returned invalid JSON data.") from None
    return APIResponse(response.status, data, response.headers)


def _query_value(value, label):
    if isinstance(value, (bool, str, int)):
        normalized = value
    elif isinstance(value, float) and math.isfinite(value):
        normalized = value
    else:
        raise ConfigurationError(f"{label} contains an unsupported query value.")
    if isinstance(normalized, str) and (
        len(normalized) > 16384 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", normalized)
    ):
        raise ConfigurationError(f"{label} contains an unsupported query value.")
    return normalized


def _query_params(params=None):
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ConfigurationError("params must be a mapping.")
    result = {}
    for key, value in params.items():
        if not isinstance(key, str) or not _QUERY_KEY.fullmatch(key):
            raise ConfigurationError("params contains an invalid key.")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if not value:
                raise ConfigurationError("params contains an empty query list.")
            result[key] = [_query_value(item, "params") for item in value]
        else:
            result[key] = _query_value(value, "params")
    return result


def _expression(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 16384
        or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value)
    ):
        raise ConfigurationError("query must be a bounded PromQL expression.")
    return value


def _remote_url(value):
    if not isinstance(value, str) or re.search(r"[\x00-\x20\x7f]", value):
        raise ConfigurationError("url must be an HTTP(S) remote-write URL.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ConfigurationError("url must be an HTTP(S) remote-write URL.") from None
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise ConfigurationError("url must be an HTTP(S) remote-write URL without credentials.")
    return value


def alerts(client, params=None, cluster_filter=False):
    """Return Alertmanager alerts proxied by Dashboard."""
    if not isinstance(cluster_filter, bool):
        raise ConfigurationError("cluster_filter must be a boolean.")
    params = _query_params(params)
    if cluster_filter:
        params["cluster_filter"] = True
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION, params=params)
    return _json_response(response, "Ceph Prometheus alerts")


def rules(client, params=None):
    """Return Prometheus rule groups proxied by Dashboard."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/rules",
        api_version=API_VERSION,
        params=_query_params(params),
    )
    return _json_response(response, "Ceph Prometheus rules")


def query_range(client, expression, start=None, end=None, step=None, params=None):
    """Run a Prometheus range query through Dashboard."""
    params = _query_params(params)
    params["params"] = _expression(expression)
    for key, value in (("start", start), ("end", end), ("step", step)):
        if value is not None:
            params[key] = _query_value(value, key)
    response = client.request(
        "GET", f"{RESOURCE_PATH}/data", api_version=API_VERSION, params=params
    )
    return _json_response(response, "Ceph Prometheus range query")


def query(client, expression, params=None):
    """Run an instant Prometheus query (current Ceph only)."""
    params = _query_params(params)
    params["params"] = _expression(expression)
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/prometheus_query_data",
        api_version=API_VERSION,
        params=params,
    )
    return _json_response(response, "Ceph Prometheus instant query")


def silences(client, params=None):
    """Return Alertmanager silences."""
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/silences",
        api_version=API_VERSION,
        params=_query_params(params),
    )
    return _json_response(response, "Ceph Prometheus silences")


def create_silence(client, silence):
    """Create an Alertmanager silence from a JSON mapping."""
    if not isinstance(silence, Mapping):
        raise ConfigurationError("silence must be a mapping.")
    silence = validation.json_value(silence, "silence")
    response = client.request(
        "POST", f"{RESOURCE_PATH}/silence", api_version=API_VERSION, data=silence
    )
    return _json_response(response, "Ceph Prometheus silence creation")


def delete_silence(client, silence_id, confirm=False):
    """Delete one Alertmanager silence after explicit confirmation."""
    silence_id = validation.identifier(
        silence_id, "silence_id", pattern=_SILENCE_ID, max_length=256
    )
    if confirm is not True:
        raise ConfigurationError("Deleting a silence requires confirm=True.")
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/silence/{quote(silence_id, safe='')}",
        api_version=API_VERSION,
    )
    return _json_response(response, "Ceph Prometheus silence deletion", allow_none=True)


def alert_groups(client, params=None, cluster_filter=False):
    """Return Alertmanager alert groups (current Ceph only)."""
    if not isinstance(cluster_filter, bool):
        raise ConfigurationError("cluster_filter must be a boolean.")
    params = _query_params(params)
    if cluster_filter:
        params["cluster_filter"] = True
    response = client.request(
        "GET", f"{RESOURCE_PATH}/alertgroup", api_version=API_VERSION, params=params
    )
    return _json_response(response, "Ceph Prometheus alert groups")


def notifications(client, from_=None):
    """Return Dashboard's process-local received alert notifications."""
    params = {}
    if from_ is not None:
        if from_ == "last":
            params["from"] = "last"
        else:
            params["from"] = validation.non_negative_integer(from_, "from_")
    response = client.request(
        "GET", f"{RESOURCE_PATH}/notifications", api_version=API_VERSION, params=params
    )
    return _json_response(response, "Ceph Prometheus notifications")


def set_remote_write(client, url, allowed_metrics):
    """Set one Prometheus remote-write target (current Ceph only)."""
    url = _remote_url(url)
    allowed_metrics = validation.string_list(
        allowed_metrics,
        "allowed_metrics",
        pattern=_METRIC_NAME,
        optional=False,
    )
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/set_remote_write",
        api_version=API_VERSION,
        data={
            "remote_write_url": url,
            "remote_write_allowed_metrics": allowed_metrics,
        },
    )
    return _json_response(response, "Ceph Prometheus remote-write update", allow_none=True)


def remove_remote_write(client, url, confirm=False):
    """Remove one Prometheus remote-write target (current Ceph only)."""
    url = _remote_url(url)
    if confirm is not True:
        raise ConfigurationError("Removing a remote-write target requires confirm=True.")
    response = client.request(
        "PUT",
        f"{RESOURCE_PATH}/remove_remote_write",
        api_version=API_VERSION,
        data={"url": url},
    )
    return _json_response(response, "Ceph Prometheus remote-write removal", allow_none=True)
