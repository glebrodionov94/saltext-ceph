"""Emit events when Ceph health or Dashboard reachability changes.

The beacon performs one ``ceph_health.minimal`` execution-module call per run.
It emits ``degraded``, ``recovered``, ``unreachable``, and ``reachable`` tags;
unchanged observations are suppressed with a fingerprint in ``__context__``.

Example configuration:

.. code-block:: yaml

    beacons:
      ceph_health:
        - profile: default
        - interval: 30
        - max_checks: 20
"""

import logging

from saltext.ceph.utils.ceph import events

log = logging.getLogger(__name__)

__virtualname__ = "ceph_health"


def __virtual__():
    return __virtualname__


def validate(config):
    """Validate list-based beacon configuration."""
    rendered, error = events.validate_config(config, {"max_checks"})
    if error:
        return False, f"Configuration for ceph_health beacon {error}."
    max_checks = rendered.get("max_checks", 20)
    if (
        isinstance(max_checks, bool)
        or not isinstance(max_checks, int)
        or not 1 <= max_checks <= 100
    ):
        return False, "Configuration for ceph_health beacon max_checks must be from 1 to 100."
    return True, "Valid beacon configuration."


def beacon(config):
    """Read compact cluster health and emit transition events."""
    valid, _ = validate(config)
    if not valid:
        return []
    rendered, error = events.validate_config(config, {"max_checks"})
    if error:
        return []
    profile = rendered.get("profile", "default")
    identity = events.instance_id(rendered)
    state = events.context_state(__context__, __virtualname__, identity)

    try:
        result = __salt__["ceph_health.minimal"](profile=profile)
        observation = events.health_observation(
            events.response_data(result), rendered.get("max_checks", 20)
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.warning("Ceph health beacon read failed (%s).", type(exc).__name__)
        if state.get("connectivity") == "unreachable":
            return []
        state["connectivity"] = "unreachable"
        return [
            {
                "tag": "unreachable",
                "profile": profile,
                "error": "Ceph Dashboard health read failed",
            }
        ]

    result_events = []
    if state.get("connectivity") == "unreachable":
        result_events.append(
            {
                "tag": "reachable",
                "profile": profile,
                "status": observation["status"],
            }
        )
    state["connectivity"] = "reachable"

    degraded = observation["status"].upper() != "HEALTH_OK"
    previous_degraded = state.get("degraded")
    previous_fingerprint = state.get("fingerprint")
    if degraded and (
        previous_degraded is not True or previous_fingerprint != observation["fingerprint"]
    ):
        result_events.append({"tag": "degraded", "profile": profile, **observation})
    elif not degraded and previous_degraded is True:
        result_events.append(
            {
                "tag": "recovered",
                "profile": profile,
                "status": observation["status"],
                "fingerprint": observation["fingerprint"],
            }
        )
    state["degraded"] = degraded
    state["fingerprint"] = observation["fingerprint"]
    return result_events
