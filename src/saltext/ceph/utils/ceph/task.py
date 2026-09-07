"""Operations and polling for Dashboard's public ``task.py`` controller."""

import re
import time
from collections.abc import Mapping
from collections.abc import Sequence

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.utils.ceph.errors import TaskFailedError
from saltext.ceph.utils.ceph.errors import TaskTimeoutError

API_VERSION = "1.0"
RESOURCE_PATH = "/api/task"
_MASK = "********"
_CREDENTIAL_PARTS = (
    "access_key",
    "accesskey",
    "authorization",
    "client_key",
    "credential",
    "dhchap",
    "keyring",
    "mfa_pin",
    "mutual_password",
    "opaque_data",
    "password",
    "private_key",
    "privatekey",
    "psk",
    "push_endpoint",
    "secret",
    "token",
)


def _include_secrets(value):
    if not isinstance(value, bool):
        raise ConfigurationError("include_secrets must be a boolean.")
    return value


def _credential_key(value):
    normalized = str(value).casefold().replace("-", "_").replace(" ", "_")
    return any(part in normalized for part in _CREDENTIAL_PARTS)


def _redact(value):
    if isinstance(value, Mapping):
        return {
            key: _MASK if _credential_key(key) else _redact(item) for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact(item) for item in value]
    return value


def _safe_task(value, include_secrets):
    result = dict(value) if include_secrets else _redact(value)
    if not include_secrets:
        result.pop("exception", None)
        result.pop("ret_value", None)
    return result


def _task_name(value, optional=False):
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 255
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError("name must be a bounded task name.")
    return value


def _tasks(response, include_secrets=False):
    include_secrets = _include_secrets(include_secrets)
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph task list returned an unexpected response shape.")
    result = dict(response.data)
    for key in ("executing_tasks", "finished_tasks"):
        values = result.get(key)
        if not isinstance(values, list) or not all(isinstance(item, Mapping) for item in values):
            raise ProtocolError("Ceph task list returned an unexpected response shape.")
        result[key] = [_safe_task(item, include_secrets) for item in values]
    return APIResponse(response.status, result, response.headers)


def list_(client, name=None, include_secrets=False):
    """Return executing and finished Dashboard tasks, optionally by name."""
    name = _task_name(name, optional=True)
    include_secrets = _include_secrets(include_secrets)
    params = {"name": name} if name is not None else {}
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION, params=params)
    return _tasks(response, include_secrets)


def _matches(task, name, metadata):
    if task.get("name") != name or not isinstance(task.get("metadata"), Mapping):
        return False
    return all(task["metadata"].get(key) == value for key, value in metadata.items())


def wait(
    client,
    name,
    metadata=None,
    timeout=300.0,
    interval=2.0,
    fail_on_error=True,
    include_secrets=False,
):
    """Poll until the newest task matching name and metadata has finished."""
    name = _task_name(name)
    if metadata is None:
        metadata = {}
    metadata = validation.json_value(metadata, "metadata")
    if not isinstance(metadata, Mapping):
        raise ConfigurationError("metadata must be a mapping.")
    for label, value in (("timeout", timeout), ("interval", interval)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 < float(value) <= (86400 if label == "timeout" else 60)
        ):
            maximum = "86400" if label == "timeout" else "60"
            raise ConfigurationError(
                f"{label} must be a positive number no greater than {maximum}."
            )
    if not isinstance(fail_on_error, bool):
        raise ConfigurationError("fail_on_error must be a boolean.")
    include_secrets = _include_secrets(include_secrets)

    deadline = time.monotonic() + float(timeout)
    while True:
        # Match against the original metadata, then sanitize only the returned task.
        tasks = list_(client, name, include_secrets=True).data
        executing = [item for item in tasks["executing_tasks"] if _matches(item, name, metadata)]
        finished = [item for item in tasks["finished_tasks"] if _matches(item, name, metadata)]
        if not executing and finished:
            task = finished[0]
            if not isinstance(task.get("success"), bool):
                raise ProtocolError("Ceph finished task returned an unexpected response shape.")
            if fail_on_error and not task["success"]:
                raise TaskFailedError(f"Ceph task {name!r} failed.")
            return APIResponse(200, _safe_task(task, include_secrets))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TaskTimeoutError(f"Ceph task {name!r} did not finish before timeout.")
        time.sleep(min(float(interval), remaining))


def wait_response(
    client,
    response,
    timeout=300.0,
    interval=2.0,
    fail_on_error=True,
    include_secrets=False,
):
    """Return a synchronous response or wait for a task described by a 202 body."""
    include_secrets = _include_secrets(include_secrets)
    if not isinstance(response, APIResponse):
        raise ConfigurationError("response must be an APIResponse.")
    if response.status != 202:
        return response
    if not isinstance(response.data, Mapping):
        raise ProtocolError("Ceph task response returned an unexpected response shape.")
    name = response.data.get("name")
    metadata = response.data.get("metadata", {})
    return wait(
        client,
        name,
        metadata,
        timeout,
        interval,
        fail_on_error,
        include_secrets,
    )
