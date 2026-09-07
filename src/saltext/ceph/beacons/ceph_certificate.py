"""Emit threshold transitions for certificates known to cephadm.

One certificate-list request is made per run. Events contain certificate
metadata only; PEM data, private keys, detailed subjects, and API error bodies
are never retained or emitted.

Example configuration:

.. code-block:: yaml

    beacons:
      ceph_certificate:
        - profile: default
        - interval: 3600
        - warning_days: 30
        - critical_days: 7
        - include_cephadm_signed: true
"""

import logging
import re

from saltext.ceph.utils.ceph import events

log = logging.getLogger(__name__)

__virtualname__ = "ceph_certificate"

_SCOPES = frozenset(("service", "host", "global"))
_SERVICE_TYPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.*?-]*")


def __virtual__():
    return __virtualname__


def validate(config):
    """Validate list-based beacon configuration."""
    rendered, error = events.validate_config(
        config,
        {
            "critical_days",
            "include_cephadm_signed",
            "scope",
            "service_type",
            "warning_days",
        },
    )
    if error:
        return False, f"Configuration for ceph_certificate beacon {error}."

    for option, default in (("warning_days", 30), ("critical_days", 7)):
        value = rendered.get(option, default)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3650:
            return False, (
                f"Configuration for ceph_certificate beacon {option} " "must be from 0 to 3650."
            )
    if rendered.get("critical_days", 7) > rendered.get("warning_days", 30):
        return False, (
            "Configuration for ceph_certificate beacon critical_days "
            "must not exceed warning_days."
        )
    scope = rendered.get("scope")
    if scope is not None and (not isinstance(scope, str) or scope.lower() not in _SCOPES):
        return False, (
            "Configuration for ceph_certificate beacon scope must be service, host, or global."
        )
    service_type = rendered.get("service_type")
    if service_type is not None and (
        not isinstance(service_type, str) or not _SERVICE_TYPE.fullmatch(service_type)
    ):
        return False, (
            "Configuration for ceph_certificate beacon service_type contains "
            "unsupported characters."
        )
    if not isinstance(rendered.get("include_cephadm_signed", True), bool):
        message = "ceph_certificate include_cephadm_signed must be a boolean."
        return False, message
    return True, "Valid beacon configuration."


def beacon(config):
    """Read certificate metadata once and emit severity transitions."""
    valid, _ = validate(config)
    if not valid:
        return []
    rendered, error = events.validate_config(
        config,
        {
            "critical_days",
            "include_cephadm_signed",
            "scope",
            "service_type",
            "warning_days",
        },
    )
    if error:
        return []
    profile = rendered.get("profile", "default")
    identity = events.instance_id(rendered)
    state = events.context_state(__context__, __virtualname__, identity)

    try:
        result = __salt__["ceph_certificates.list"](
            status=None,
            scope=rendered.get("scope"),
            service_type=rendered.get("service_type"),
            include_cephadm_signed=rendered.get("include_cephadm_signed", True),
            profile=profile,
        )
        entries = events.bounded_certificates(events.response_data(result))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.warning("Ceph certificate beacon read failed (%s).", type(exc).__name__)
        return []

    previous = state.get("levels")
    previous = previous if isinstance(previous, dict) else {}
    current = {}
    observations = []
    now = events.utcnow()
    for entry in entries:
        try:
            cert_id, level, observation = events.certificate_observation(
                entry,
                rendered.get("warning_days", 30),
                rendered.get("critical_days", 7),
                now,
            )
        except ValueError:
            continue
        current[cert_id] = level
        observations.append((cert_id, level, observation))

    result_events = []
    for cert_id, level, observation in observations:
        old_level = previous.get(cert_id)
        if level in ("warning", "critical", "expired") and old_level != level:
            result_events.append({"tag": level, "profile": profile, **observation})
        elif level == "healthy" and old_level in ("warning", "critical", "expired"):
            result_events.append({"tag": "recovered", "profile": profile, **observation})
    state["levels"] = current
    return result_events
