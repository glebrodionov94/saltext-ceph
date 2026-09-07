"""Shared validation and transport helpers for current Ceph NVMe-oF APIs."""

import ipaddress
import re
import uuid as uuid_module
from collections.abc import Mapping
from collections.abc import Sequence
from urllib.parse import quote

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError

API_VERSION = "1.0"
BASE_PATH = "/api/nvmeof"
MAX_NSID = (1 << 32) - 1
MAX_UINT32 = (1 << 32) - 1

_NQN = re.compile(r"nqn\.[A-Za-z0-9][A-Za-z0-9_.:-]*")
_SECRET_KEYS = frozenset(
    (
        "dhchap_key",
        "dhchap_controller_key",
        "dhchap_ctrlr_key",
        "key",
        "password",
        "psk",
        "secret",
        "token",
    )
)


def text(value, label, *, optional=False, allow_empty=False, max_length=1024):
    """Validate bounded single-line text without disclosing the value in errors."""
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or len(value) > max_length
        or (not value and not allow_empty)
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError(f"{label} must be bounded single-line text.")
    return value


def identifier(value, label):
    """Validate a Ceph or gateway identifier."""
    return validation.identifier(value, label)


def nqn(value, label="nqn", *, wildcard=False):
    """Validate a bounded ASCII NVMe qualified name."""
    if wildcard and value == "*":
        return value
    if (
        not isinstance(value, str)
        or len(value.encode("utf-8")) > 223
        or not value.isascii()
        or not _NQN.fullmatch(value)
    ):
        raise ConfigurationError(f"{label} must be a valid NVMe qualified name.")
    return value


def boolean(value, label):
    """Require an exact JSON boolean."""
    if not isinstance(value, bool):
        raise ConfigurationError(f"{label} must be a boolean.")
    return value


def confirmed(value, action):
    """Require explicit confirmation for a disruptive operation."""
    boolean(value, "confirm")
    if not value:
        raise ConfigurationError(f"{action} requires confirm=True.")


def integer(value, label, *, minimum=0, maximum=MAX_UINT32):
    """Validate a bounded integer while excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise ConfigurationError(f"{label} must be an integer from {minimum} to {maximum}.")
    return value


def namespace_id(value, label="nsid", *, optional=False):
    """Normalize a namespace ID to the decimal string used by the controller."""
    if value is None and optional:
        return None
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        value = int(value)
    value = integer(value, label, minimum=1, maximum=MAX_NSID)
    return str(value)


def uuid_value(value, label="uuid", *, optional=False):
    """Normalize a canonical UUID."""
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ConfigurationError(f"{label} must be a canonical UUID.")
    try:
        normalized = str(uuid_module.UUID(value))
    except ValueError:
        raise ConfigurationError(f"{label} must be a canonical UUID.") from None
    if value.lower() != normalized:
        raise ConfigurationError(f"{label} must be a canonical UUID.")
    return normalized


def ip_address(value, label="traddr"):
    """Normalize a unicast IPv4 or IPv6 transport address."""
    try:
        address = ipaddress.ip_address(value)
    except (TypeError, ValueError):
        raise ConfigurationError(f"{label} must be an IP address.") from None
    if address.is_unspecified or address.is_multicast:
        raise ConfigurationError(f"{label} must be a unicast IP address.")
    return str(address)


def address_family(value, address=None):
    """Validate Dashboard's numeric address family and an optional address."""
    value = integer(value, "adrfam", minimum=0, maximum=1)
    if address is not None:
        version = ipaddress.ip_address(address).version
        if (value == 0 and version != 4) or (value == 1 and version != 6):
            raise ConfigurationError("adrfam does not match traddr.")
    return value


def port(value, label="port", *, optional=False):
    """Validate a TCP port."""
    if value is None and optional:
        return None
    return integer(value, label, minimum=1, maximum=65535)


def network(value, label="network_mask"):
    """Normalize an IPv4 or IPv6 network mask."""
    try:
        return str(ipaddress.ip_network(value, strict=False))
    except (TypeError, ValueError):
        raise ConfigurationError(f"{label} must be an IP network in CIDR form.") from None


def string_list(values, label, *, allowed=None, optional=True):
    """Validate a duplicate-free list of bounded single-line strings."""
    if values is None and optional:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ConfigurationError(f"{label} must be a non-empty list.")
    result = [text(value, label, max_length=255) for value in values]
    if len(set(result)) != len(result):
        raise ConfigurationError(f"{label} must not contain duplicates.")
    if allowed is not None and not {value.upper() for value in result}.issubset(allowed):
        raise ConfigurationError(f"{label} contains an unsupported value.")
    return result


def routing(gw_group=None, server_address=None, traddr=None, *, require_address=False):
    """Validate common gateway selection fields and reject ambiguous addresses."""
    result = {}
    if gw_group is not None:
        result["gw_group"] = identifier(gw_group, "gw_group")
    if server_address is not None:
        server_address = text(server_address, "server_address", max_length=512).strip()
        if not server_address:
            raise ConfigurationError("server_address must not be blank.")
        result["server_address"] = server_address
    if traddr is not None:
        traddr = text(traddr, "traddr", max_length=512).strip()
        if not traddr:
            raise ConfigurationError("traddr must not be blank.")
        result["traddr"] = traddr
    if server_address is not None and traddr is not None:
        raise ConfigurationError("server_address and deprecated traddr are mutually exclusive.")
    if require_address and server_address is None and traddr is None:
        raise ConfigurationError("server_address or deprecated traddr is required.")
    return result


def encoded(value):
    """Encode one already validated path segment."""
    return quote(str(value), safe="")


def _strip_secrets(value):
    if isinstance(value, Mapping):
        return {
            key: _strip_secrets(child)
            for key, child in value.items()
            if str(key).lower() not in _SECRET_KEYS
        }
    if isinstance(value, list):
        return [_strip_secrets(child) for child in value]
    return value


def protected_response(response, label="Ceph NVMe-oF endpoint"):
    """Detach JSON response data and recursively remove credential fields."""
    data = validation.json_value(response.data, label)
    return APIResponse(response.status, _strip_secrets(data), response.headers)


def request(client, method, path, *, params=None, data=None, label="Ceph NVMe-oF endpoint"):
    """Issue one current public NVMe-oF request without retries or task polling."""
    kwargs = {}
    if params:
        kwargs["params"] = params
    if data is not None:
        kwargs["data"] = data
    response = client.request(method, path, api_version=API_VERSION, **kwargs)
    return protected_response(response, label)
