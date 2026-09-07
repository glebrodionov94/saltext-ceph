"""Emit one event for each newly finished Ceph Dashboard task.

The first run establishes a baseline by default. Set ``emit_existing: true`` to
emit events for finished tasks already returned at startup. Failed tasks are the
default signal; set ``failures_only: false`` to also receive ``succeeded`` tags.

Example configuration:

.. code-block:: yaml

    beacons:
      ceph_task:
        - profile: default
        - interval: 10
        - failures_only: true
        - cache_size: 256
"""

import logging
import re
from collections.abc import Mapping

from saltext.ceph.utils.ceph import events

log = logging.getLogger(__name__)

__virtualname__ = "ceph_task"


def __virtual__():
    return __virtualname__


def validate(config):
    """Validate list-based beacon configuration."""
    rendered, error = events.validate_config(
        config, {"cache_size", "emit_existing", "failures_only", "name"}
    )
    if error:
        return False, f"Configuration for ceph_task beacon {error}."

    name = rendered.get("name")
    if name is not None and (
        not isinstance(name, str)
        or not name
        or len(name) > 255
        or re.search(r"[\x00-\x1f\x7f]", name)
    ):
        return False, "Configuration for ceph_task beacon name must be a bounded string."
    for option, default in (("failures_only", True), ("emit_existing", False)):
        if not isinstance(rendered.get(option, default), bool):
            return False, f"Configuration for ceph_task beacon {option} must be a boolean."
    cache_size = rendered.get("cache_size", 256)
    if (
        isinstance(cache_size, bool)
        or not isinstance(cache_size, int)
        or not 1 <= cache_size <= 256
    ):
        return False, "Configuration for ceph_task beacon cache_size must be from 1 to 256."
    return True, "Valid beacon configuration."


def beacon(config):
    """Read the task collection once and emit new completion events."""
    valid, _ = validate(config)
    if not valid:
        return []
    rendered, error = events.validate_config(
        config, {"cache_size", "emit_existing", "failures_only", "name"}
    )
    if error:
        return []
    profile = rendered.get("profile", "default")
    cache_size = rendered.get("cache_size", 256)
    identity = events.instance_id(rendered)
    state = events.context_state(__context__, __virtualname__, identity)

    try:
        result = __salt__["ceph_task.list"](name=rendered.get("name"), profile=profile)
        data = events.response_data(result)
        if not isinstance(data, Mapping) or not isinstance(data.get("finished_tasks"), list):
            raise ValueError("task response has an unexpected shape")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.warning("Ceph task beacon read failed (%s).", type(exc).__name__)
        return []

    # Dashboard returns newest tasks first. Cap before processing so both work
    # and retained identity state remain bounded by cache_size.
    tasks = list(reversed(data["finished_tasks"][:cache_size]))
    observed = []
    for task in tasks:
        try:
            task_id = events.task_identity(task)
        except ValueError:
            continue
        observed.append((task_id, task))

    seen = state.get("seen")
    initialized = isinstance(seen, list) and state.get("initialized") is True
    seen = [item for item in seen or [] if isinstance(item, str)][-cache_size:]
    seen_set = set(seen)
    emit_existing = rendered.get("emit_existing", False)
    failures_only = rendered.get("failures_only", True)
    result_events = []
    for task_id, task in observed:
        if task_id not in seen_set and (initialized or emit_existing):
            if not failures_only or task["success"] is False:
                result_events.append(
                    {
                        "tag": "succeeded" if task["success"] else "failed",
                        "profile": profile,
                        **events.task_event(task),
                    }
                )
        if task_id in seen_set:
            seen.remove(task_id)
        seen.append(task_id)
        seen_set.add(task_id)

    state["seen"] = seen[-cache_size:]
    state["initialized"] = True
    return result_events
