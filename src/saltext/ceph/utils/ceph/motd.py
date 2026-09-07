"""Operations from the public controller registered by Dashboard's MOTD plugin."""

import re
from collections.abc import Mapping

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/motd"
_SEVERITIES = frozenset(("info", "warning", "danger"))
_DURATION = re.compile(r"-?[1-9][0-9]{0,8}[smhdw]", re.IGNORECASE)


def _response(response):
    if response.data is not None and not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph Dashboard MOTD returned an unexpected response shape.")
    data = dict(response.data) if isinstance(response.data, Mapping) else None
    return APIResponse(response.status, data, response.headers)


def create(client, severity, expires, message):
    """Set the current-only Dashboard message of the day."""
    if not isinstance(severity, str) or severity not in _SEVERITIES:
        raise ConfigurationError("severity must be info, warning, or danger.")
    if not isinstance(expires, str) or (expires != "0" and not _DURATION.fullmatch(expires)):
        raise ConfigurationError("expires must be 0 or a bounded duration such as 30s, 2h, or 10d.")
    try:
        message_size = len(message.encode("utf-8")) if isinstance(message, str) else 0
    except UnicodeEncodeError:
        message_size = 65537
    if not isinstance(message, str) or not message or message_size > 65536 or "\x00" in message:
        raise ConfigurationError("message must be non-empty UTF-8 text of at most 64 KiB.")
    response = client.request(
        "POST",
        RESOURCE_PATH,
        api_version=API_VERSION,
        data={"severity": severity, "expires": expires, "message": message},
    )
    return _response(response)


def clear(client, confirm=False):
    """Clear the current-only Dashboard message of the day."""
    validation.confirmation(confirm, "Clearing the Dashboard message of the day")
    response = client.request("DELETE", f"{RESOURCE_PATH}/clear", api_version=API_VERSION)
    return _response(response)
