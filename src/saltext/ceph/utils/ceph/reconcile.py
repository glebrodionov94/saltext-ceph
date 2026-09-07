"""Pure helpers shared by declarative Ceph state modules."""

import time
from collections.abc import Mapping

from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError


def state_result(name):
    """Return Salt's standard initial state result."""
    return {"name": name, "changes": {}, "result": False, "comment": ""}


def envelope(value, label="Ceph operation"):
    """Validate and detach an execution-module API envelope."""
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{label} returned an invalid Salt envelope.")
    status = value.get("status")
    if isinstance(status, bool) or not isinstance(status, int) or not 200 <= status < 300:
        raise ProtocolError(f"{label} returned an invalid Salt envelope.")
    headers = value.get("headers", {})
    if not isinstance(headers, Mapping):
        raise ProtocolError(f"{label} returned an invalid Salt envelope.")
    return {"status": status, "data": value.get("data"), "headers": dict(headers)}


def data(value, label="Ceph read", expected=None):
    """Return data from a validated envelope and optionally enforce its type."""
    result = envelope(value, label)
    if expected is not None and not isinstance(result["data"], expected):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    return result["data"]


def wait_if_accepted(
    salt,
    response,
    *,
    profile="default",
    timeout=300.0,
    interval=2.0,
):
    """Wait for a Dashboard task when a mutation returned HTTP 202."""
    result = envelope(response, "Ceph mutation")
    if result["status"] != 202:
        return result
    reference = result["data"]
    if not isinstance(reference, Mapping) or not isinstance(reference.get("name"), str):
        raise ProtocolError("Ceph mutation returned an invalid task reference.")
    metadata = reference.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ProtocolError("Ceph mutation returned an invalid task reference.")
    waiter = salt.get("ceph_task.wait")
    if waiter is None:
        raise ConfigurationError("ceph_task.wait is required for asynchronous reconciliation.")
    return envelope(
        waiter(
            reference["name"],
            metadata=dict(metadata),
            timeout=timeout,
            interval=interval,
            fail_on_error=True,
            profile=profile,
        ),
        "Ceph task wait",
    )


def wait_for_convergence(
    read,
    converged,
    *,
    timeout=300.0,
    interval=2.0,
    timeout_message="Ceph resource did not converge before timeout.",
):
    """Poll an eventually consistent read until its declared state is visible."""
    for label, value, maximum in (
        ("timeout", timeout, 86400),
        ("interval", interval, 60),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 < float(value) <= maximum
        ):
            raise ConfigurationError(
                f"{label} must be a positive number no greater than {maximum}."
            )
    if not callable(read) or not callable(converged):
        raise ConfigurationError("Convergence read and predicate must be callable.")
    if not isinstance(timeout_message, str) or not timeout_message:
        raise ConfigurationError("Convergence timeout message must be a non-empty string.")

    deadline = time.monotonic() + float(timeout)
    while True:
        value = read()
        if converged(value):
            return value
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProtocolError(timeout_message)
        time.sleep(min(float(interval), remaining))


def project(current, desired):
    """Project current data onto keys explicitly managed by a desired mapping."""
    if not isinstance(current, Mapping) or not isinstance(desired, Mapping):
        raise ProtocolError("Managed resource comparison requires mappings.")
    result = {}
    for key, wanted in desired.items():
        actual = current.get(key)
        if isinstance(wanted, Mapping) and isinstance(actual, Mapping):
            result[key] = project(actual, wanted)
        else:
            result[key] = actual
    return result


def no_change(ret, comment):
    """Mark a state as already converged."""
    ret["result"] = True
    ret["comment"] = comment
    return ret


def planned(ret, old, new, comment):
    """Describe a pending test-mode change."""
    ret["result"] = None
    ret["changes"] = {"old": old, "new": new}
    ret["comment"] = comment
    return ret


def changed(ret, old, new, comment):
    """Describe a verified applied change."""
    ret["result"] = True
    ret["changes"] = {"old": old, "new": new}
    ret["comment"] = comment
    return ret


def failed(ret, exc):
    """Convert a sanitized exception into a normal Salt state failure."""
    ret["result"] = False
    ret["comment"] = str(exc)
    return ret
