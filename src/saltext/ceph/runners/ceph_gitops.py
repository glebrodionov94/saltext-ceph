"""Plan and apply Ceph states through one explicitly selected control minion.

The runner uses Salt's ``list`` target type with a one-item list.  It verifies
the cluster FSID before state compilation and refuses to overlap state runs on
the same minion.  Profile credentials remain in that minion's pillar and are
never submitted as runner arguments or stored in the master job cache.
"""

import re
import uuid
from collections.abc import Mapping

import salt.client
from salt.exceptions import SaltClientError
from salt.exceptions import SaltRunnerError

__virtualname__ = "ceph_gitops"

_ACTIVE_KEY = "saltext.ceph.gitops.active"
_STATE_FUNCTION_PREFIXES = ("state.",)
_SAFE_STATE_FUNCTION = re.compile(r"state\.[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_SAFE_JID = re.compile(r"[0-9]{1,32}\Z")


def __virtual__():
    return __virtualname__


def _minion_id(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 255
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise SaltRunnerError("control_minion must be a bounded Salt minion ID.")
    return value


def _fsid(value):
    if not isinstance(value, str):
        raise SaltRunnerError("expected_fsid must be a UUID string.")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise SaltRunnerError("expected_fsid must be a UUID string.") from None


def _timeout(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < float(value) <= 86400
    ):
        raise SaltRunnerError("timeout must be a positive number no greater than 86400.")
    return float(value)


def _mods(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)) or not value:
        raise SaltRunnerError("mods must be a non-empty SLS name or list of SLS names.")
    result = []
    for item in value:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > 255
            or re.search(r"[\x00-\x20\x7f]", item)
        ):
            raise SaltRunnerError("mods contains an invalid SLS name.")
        result.append(item)
    return result


def _saltenv(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or re.search(r"[\x00-\x20\x7f]", value)
    ):
        raise SaltRunnerError("saltenv must be a bounded environment name.")
    return value


def _command(control_minion, function, *, kwarg=None, timeout=60.0):
    """Run one command with an exact one-item list target."""
    try:
        with salt.client.LocalClient(__opts__.get("conf_file")) as client:
            response = client.cmd(
                [control_minion],
                function,
                arg=(),
                kwarg=kwarg or {},
                timeout=timeout,
                tgt_type="list",
            )
    except (OSError, RuntimeError, SaltClientError) as exc:
        raise SaltRunnerError("Salt master could not execute the minion command.") from exc
    if not isinstance(response, Mapping) or set(response) != {control_minion}:
        raise SaltRunnerError("Expected a response from exactly the selected control minion.")
    return response[control_minion]


def _running(control_minion, timeout):
    jobs = _command(control_minion, "saltutil.running", timeout=timeout)
    if not isinstance(jobs, list):
        raise SaltRunnerError("The control minion returned an invalid running-job list.")
    result = []
    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        function = job.get("fun")
        if not isinstance(function, str) or not function.startswith(_STATE_FUNCTION_PREFIXES):
            continue

        # ``saltutil.running`` includes the original ``arg`` and ``kwarg`` in
        # some Salt versions. They can contain inline pillar or other secrets,
        # so expose only the fields needed to identify an active state job.
        safe = {"fun": function if _SAFE_STATE_FUNCTION.fullmatch(function) else "state.<unknown>"}
        jid = job.get("jid")
        if not isinstance(jid, bool) and _SAFE_JID.fullmatch(str(jid)):
            safe["jid"] = str(jid)
        pid = job.get("pid")
        if isinstance(pid, int) and not isinstance(pid, bool) and pid >= 0:
            safe["pid"] = pid
        result.append(safe)
    return result


def running(control_minion, timeout=60.0):
    """Return active state jobs on exactly one control minion."""
    control_minion = _minion_id(control_minion)
    return _running(control_minion, _timeout(timeout))


def _verify_cluster(control_minion, expected_fsid, timeout):
    response = _command(control_minion, "ceph_health.fsid", timeout=timeout)
    if not isinstance(response, Mapping) or response.get("status") != 200:
        raise SaltRunnerError("The control minion returned an invalid Ceph FSID response.")
    actual = response.get("data")
    try:
        actual = str(uuid.UUID(actual)) if isinstance(actual, str) else None
    except ValueError:
        actual = None
    if actual != expected_fsid:
        raise SaltRunnerError("The selected control minion is connected to a different cluster.")


def _run(test, control_minion, expected_fsid, mods, saltenv, timeout):
    control_minion = _minion_id(control_minion)
    expected_fsid = _fsid(expected_fsid)
    mods = _mods(mods)
    saltenv = _saltenv(saltenv)
    timeout = _timeout(timeout)

    active = __context__.setdefault(_ACTIVE_KEY, set())
    if not isinstance(active, set):
        raise SaltRunnerError("The GitOps runner context is invalid.")
    if control_minion in active:
        raise SaltRunnerError("A GitOps run is already active for this control minion.")
    active.add(control_minion)
    try:
        if _running(control_minion, timeout):
            raise SaltRunnerError("A state run is already active on the control minion.")
        _verify_cluster(control_minion, expected_fsid, timeout)
        kwargs = {"test": test, "saltenv": saltenv, "queue": False}
        if mods is not None:
            kwargs["mods"] = mods
        return _command(
            control_minion,
            "state.apply",
            kwarg=kwargs,
            timeout=timeout,
        )
    finally:
        active.discard(control_minion)


def plan(control_minion, expected_fsid, mods=None, saltenv="base", timeout=300.0):
    """Run ``state.apply test=true`` after target and cluster verification."""
    return _run(True, control_minion, expected_fsid, mods, saltenv, timeout)


def apply(control_minion, expected_fsid, mods=None, saltenv="base", timeout=300.0):
    """Apply Ceph states after target, concurrency and cluster verification."""
    return _run(False, control_minion, expected_fsid, mods, saltenv, timeout)
