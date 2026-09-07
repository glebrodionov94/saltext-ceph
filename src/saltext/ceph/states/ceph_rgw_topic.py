"""Declaratively reconcile current-Ceph RGW notification topics."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph import rgw_state
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_rgw_topic"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_rgw_topic.list_topics",
        "ceph_rgw_topic.create_topic",
        "ceph_rgw_topic.delete_topic",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _wait(response, profile, timeout, interval):
    return reconcile.wait_if_accepted(
        __salt__, response, profile=profile, timeout=timeout, interval=interval
    )


def _topic(name, owner, profile):
    values = reconcile.data(
        __salt__["ceph_rgw_topic.list_topics"](include_secrets=False, profile=profile),
        "RGW topic list",
        expected=list,
    )
    values = rgw_state.list_of_mappings(values, "RGW topic list")
    matches = [
        item
        for item in values
        if item.get("name") == name and (owner is None or item.get("owner") == owner)
    ]
    if len(matches) > 1:
        raise ProtocolError(f"RGW topic list returned duplicate topic {name}.")
    return matches[0] if matches else None


def _topic_view(current, desired):
    if current is None:
        return None
    destination = current.get("dest", {})
    if not isinstance(destination, Mapping):
        raise ProtocolError("RGW topic read returned an invalid destination.")
    result = {"name": current.get("name"), "owner": current.get("owner")}
    aliases = {
        "persistent": "persistent",
        "time_to_live": "time_to_live",
        "max_retries": "max_retries",
        "retry_sleep_duration": "retry_sleep_duration",
    }
    for key, current_key in aliases.items():
        if key not in desired:
            continue
        if current_key not in destination:
            raise ProtocolError(f"RGW topic read omitted managed field {key}.")
        value = destination[current_key]
        if key == "persistent":
            value = rgw_state.response_bool(value, key)
        elif value is not None:
            value = str(value)
        result[key] = value
    if "policy" in desired:
        result["policy"] = rgw_state.json_value(current.get("policy") or {}, "topic policy")
    return result


def _desired(name, owner, persistent, time_to_live, max_retries, retry_sleep_duration, policy):
    desired = {
        "name": common.name(name, "name"),
        "owner": common.name(owner, "owner"),
        "persistent": common.boolean(persistent, "persistent"),
    }
    for key, value in {
        "time_to_live": time_to_live,
        "max_retries": max_retries,
        "retry_sleep_duration": retry_sleep_duration,
    }.items():
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ConfigurationError(f"{key} must be text or an integer.")
            desired[key] = common.name(str(value), key)
    if policy is not None:
        desired["policy"] = rgw_state.json_value(policy, "policy", mapping_only=True)
    return desired


def present(
    name,
    owner,
    push_endpoint_source=None,
    opaque_data_source=None,
    persistent=False,
    time_to_live=None,
    max_retries=None,
    retry_sleep_duration=None,
    policy=None,
    daemon_name=None,
    verify_ssl=False,
    cloud_events=False,
    ca_location=None,
    amqp_exchange=None,
    ack_level=None,
    use_ssl=False,
    kafka_brokers=None,
    mechanism=None,
    replace=False,
    confirm_replace=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph topic's stable metadata projection exists.

    Endpoint credentials and transport-specific settings are creation-only:
    Ceph masks or flattens them in metadata. The public controller has no topic
    update endpoint, so readable drift requires ``replace=True`` and
    ``confirm_replace=True``. Secret file contents never enter state changes.
    """
    ret = reconcile.state_result(name)
    try:
        desired = _desired(
            name,
            owner,
            persistent,
            time_to_live,
            max_retries,
            retry_sleep_duration,
            policy,
        )
        name = desired["name"]
        owner = desired["owner"]
        daemon_name = common.optional_text(daemon_name, "daemon_name")
        for label, value in (
            ("verify_ssl", verify_ssl),
            ("cloud_events", cloud_events),
            ("use_ssl", use_ssl),
            ("replace", replace),
            ("confirm_replace", confirm_replace),
        ):
            common.boolean(value, label)
        for label, value in (
            ("ca_location", ca_location),
            ("amqp_exchange", amqp_exchange),
            ("ack_level", ack_level),
            ("kafka_brokers", kafka_brokers),
            ("mechanism", mechanism),
        ):
            common.optional_text(value, label)
        rgw_state.validate_secret_sources(push_endpoint_source, opaque_data_source)
        current = _topic(name, owner, profile)
        old = _topic_view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"RGW topic {owner}:{name} is current.")
        if current is not None and not replace:
            raise ConfigurationError(
                "Existing topic drift requires replace=True because Ceph exposes no update endpoint."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"RGW topic {owner}:{name} would be reconciled."
            )
        if current is not None:
            if not confirm_replace:
                raise ConfigurationError("Replacing an RGW topic requires confirm_replace=True.")
            key = current.get("key")
            if not isinstance(key, str) or not key:
                raise ProtocolError("RGW topic read omitted its deletion key.")
            _wait(
                __salt__["ceph_rgw_topic.delete_topic"](key, confirm=True, profile=profile),
                profile,
                task_timeout,
                task_interval,
            )
        policy_text = (
            None
            if "policy" not in desired
            else rgw_state.json_text(desired["policy"], "policy", mapping_only=True)
        )
        response = __salt__["ceph_rgw_topic.create_topic"](
            name,
            daemon_name=daemon_name,
            owner=owner,
            push_endpoint_source=push_endpoint_source,
            opaque_data_source=opaque_data_source,
            persistent=persistent,
            time_to_live=time_to_live,
            max_retries=max_retries,
            retry_sleep_duration=retry_sleep_duration,
            policy=policy_text,
            verify_ssl=verify_ssl,
            cloud_events=cloud_events,
            ca_location=ca_location,
            amqp_exchange=amqp_exchange,
            ack_level=ack_level,
            use_ssl=use_ssl,
            kafka_brokers=kafka_brokers,
            mechanism=mechanism,
            include_secrets=False,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _topic_view(_topic(name, owner, profile), desired)
        if after != desired:
            raise ProtocolError(f"RGW topic {owner}:{name} did not converge.")
        return reconcile.changed(ret, old, after, f"RGW topic {owner}:{name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    owner=None,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure a current-Ceph RGW topic is absent."""
    ret = reconcile.state_result(name)
    try:
        name = common.name(name, "name")
        owner = common.optional_text(owner, "owner")
        confirm = common.boolean(confirm, "confirm")
        current = _topic(name, owner, profile)
        if current is None:
            return reconcile.no_change(ret, f"RGW topic {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RGW topic {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RGW topic requires confirm=True.")
        key = current.get("key")
        if not isinstance(key, str) or not key:
            raise ProtocolError("RGW topic read omitted its deletion key.")
        response = __salt__["ceph_rgw_topic.delete_topic"](key, confirm=True, profile=profile)
        _wait(response, profile, task_timeout, task_interval)
        if _topic(name, owner, profile) is not None:
            raise ProtocolError(f"RGW topic {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RGW topic {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
