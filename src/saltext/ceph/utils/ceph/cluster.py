"""Cluster status and cephadm upgrade operations from ``cluster.py``."""

import re
from collections.abc import Mapping
from collections.abc import Sequence

from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

CLUSTER_API_VERSION = "0.1"
UPGRADE_API_VERSION = "1.0"
CLUSTER_PATH = "/api/cluster"
UPGRADE_PATH = f"{CLUSTER_PATH}/upgrade"
CLUSTER_STATUSES = frozenset(("INSTALLED", "POST_INSTALLED"))
_IMAGE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/@:+-]*")
_VERSION_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}(?:[-+~][A-Za-z0-9._+-]+)?")
_DAEMON_TYPE_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
_SERVICE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def _optional_image(image):
    if image is None:
        return None
    if (
        not isinstance(image, str)
        or len(image) > 512
        or not _IMAGE_PATTERN.fullmatch(image)
        or "://" in image
    ):
        raise ConfigurationError("image must be a valid container image reference.")
    return image


def _optional_version(version):
    if version is None:
        return None
    if not isinstance(version, str) or not _VERSION_PATTERN.fullmatch(version):
        raise ConfigurationError("version must use Ceph's numeric X.Y.Z form.")
    return version


def _optional_list(values, label, pattern):
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError(f"{label} must be a non-empty list of names.")
    normalized = []
    for value in values:
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ConfigurationError(f"{label} contains an invalid name.")
        normalized.append(value)
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError(f"{label} must not contain duplicates.")
    return normalized


def _optional_placement(value):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 2048
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError("host_placement must be a non-empty single-line placement string.")
    return value


def status(client):
    """Return the Dashboard installation status marker."""
    response = client.request("GET", CLUSTER_PATH, api_version=CLUSTER_API_VERSION)
    if (
        not isinstance(response.data, Mapping)
        or response.data.get("status") not in CLUSTER_STATUSES
    ):
        raise ProtocolError("Ceph cluster status returned an unexpected response shape.")
    return APIResponse(response.status, dict(response.data), response.headers)


def set_status(client, cluster_status):
    """Set the Dashboard installation status marker."""
    if not isinstance(cluster_status, str) or cluster_status.upper() not in CLUSTER_STATUSES:
        raise ConfigurationError(f"status must be one of: {', '.join(sorted(CLUSTER_STATUSES))}.")
    return client.request(
        "PUT",
        CLUSTER_PATH,
        api_version=CLUSTER_API_VERSION,
        data={"status": cluster_status.upper()},
    )


def upgrade_list(client, tags=False, image=None, show_all_versions=False):
    """Return versions or images available to the cephadm upgrade engine."""
    params = {
        "tags": _boolean(tags, "tags"),
        "show_all_versions": _boolean(show_all_versions, "show_all_versions"),
    }
    image = _optional_image(image)
    if image is not None:
        params["image"] = image
    response = client.request("GET", UPGRADE_PATH, api_version=UPGRADE_API_VERSION, params=params)
    if not isinstance(response.data, (Mapping, list)):
        raise ProtocolError("Ceph upgrade list returned an unexpected response shape.")
    data = dict(response.data) if isinstance(response.data, Mapping) else list(response.data)
    return APIResponse(response.status, data, response.headers)


def upgrade_status(client):
    """Return current cephadm upgrade progress."""
    response = client.request("GET", f"{UPGRADE_PATH}/status", api_version=UPGRADE_API_VERSION)
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph upgrade status returned an unexpected response shape.")
    return APIResponse(response.status, dict(response.data), response.headers)


def upgrade_start(
    client,
    image=None,
    version=None,
    daemon_types=None,
    host_placement=None,
    services=None,
    limit=None,
):
    """Start an upgrade for all daemons or an explicitly filtered batch."""
    image = _optional_image(image)
    version = _optional_version(version)
    if (image is None) == (version is None):
        raise ConfigurationError("Specify exactly one of image or version.")
    daemon_types = _optional_list(daemon_types, "daemon_types", _DAEMON_TYPE_PATTERN)
    services = _optional_list(services, "services", _SERVICE_PATTERN)
    if daemon_types is not None and services is not None:
        raise ConfigurationError("daemon_types and services are mutually exclusive.")
    host_placement = _optional_placement(host_placement)
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
        raise ConfigurationError("limit must be a positive integer.")
    data = {
        key: value
        for key, value in {
            "image": image,
            "version": version,
            "daemon_types": daemon_types,
            "host_placement": host_placement,
            "services": services,
            "limit": limit,
        }.items()
        if value is not None
    }
    return client.request(
        "POST", f"{UPGRADE_PATH}/start", api_version=UPGRADE_API_VERSION, data=data
    )


def _upgrade_action(client, action):
    return client.request("PUT", f"{UPGRADE_PATH}/{action}", api_version=UPGRADE_API_VERSION)


def upgrade_pause(client):
    """Pause an active cephadm upgrade."""
    return _upgrade_action(client, "pause")


def upgrade_resume(client):
    """Resume a paused cephadm upgrade."""
    return _upgrade_action(client, "resume")


def upgrade_stop(client):
    """Stop an active cephadm upgrade."""
    return _upgrade_action(client, "stop")
