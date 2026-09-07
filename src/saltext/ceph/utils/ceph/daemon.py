"""Operations from Dashboard's public ``daemon.py`` controller."""

import re
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

LIST_API_VERSION = "1.0"
ACTION_API_VERSION = "0.1"
RESOURCE_PATH = "/api/daemon"
ACTIONS = frozenset(("start", "stop", "restart", "redeploy"))
FORCE_ACTIONS = frozenset(("stop", "restart"))
_DAEMON_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_DAEMON_TYPE_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
_IMAGE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/@:+-]*")


def _daemon_name(value):
    if not isinstance(value, str) or not _DAEMON_NAME_PATTERN.fullmatch(value):
        raise ConfigurationError("daemon_name contains unsupported characters.")
    return value


def _daemon_types(values):
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError("daemon_types must be a non-empty list of daemon types.")
    normalized = []
    for value in values:
        if not isinstance(value, str) or not _DAEMON_TYPE_PATTERN.fullmatch(value):
            raise ConfigurationError("daemon_types contains an invalid daemon type.")
        normalized.append(value)
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError("daemon_types must not contain duplicates.")
    return normalized


def _container_image(value):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 512
        or not _IMAGE_PATTERN.fullmatch(value)
        or "://" in value
    ):
        raise ConfigurationError("container_image must be a valid container image reference.")
    return value


def list_(client, daemon_types=None):
    """List orchestrator daemons, optionally filtered by daemon type."""
    daemon_types = _daemon_types(daemon_types)
    params = {"daemon_types": daemon_types} if daemon_types is not None else {}
    response = client.request("GET", RESOURCE_PATH, api_version=LIST_API_VERSION, params=params)
    if not isinstance(response.data, list) or not all(
        isinstance(item, Mapping) for item in response.data
    ):
        raise ProtocolError("Ceph daemon list returned an unexpected response shape.")
    return APIResponse(response.status, [dict(item) for item in response.data], response.headers)


def action(client, daemon_name, action_name, container_image=None, force=False):
    """Schedule a supported action for one cephadm daemon."""
    daemon_name = quote(_daemon_name(daemon_name), safe="")
    if not isinstance(action_name, str) or action_name.lower() not in ACTIONS:
        raise ConfigurationError(f"action must be one of: {', '.join(sorted(ACTIONS))}.")
    action_name = action_name.lower()
    container_image = _container_image(container_image)
    if container_image is not None and action_name != "redeploy":
        raise ConfigurationError("container_image is only valid for the redeploy action.")
    if not isinstance(force, bool):
        raise ConfigurationError("force must be a boolean.")
    if force and action_name not in FORCE_ACTIONS:
        raise ConfigurationError("force is only valid for stop and restart actions.")

    data = {"action": action_name}
    if container_image is not None:
        data["container_image"] = container_image
    if force:
        data["force"] = True
    return client.request(
        "PUT",
        f"{RESOURCE_PATH}/{daemon_name}",
        api_version=ACTION_API_VERSION,
        data=data,
    )
