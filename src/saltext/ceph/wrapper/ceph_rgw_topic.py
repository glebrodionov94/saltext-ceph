"""Manage RGW topic operations from salt-ssh."""

from saltext.ceph.utils.ceph import rgw_topic_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rgw_topic"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def create_topic(
    name,
    daemon_name=None,
    owner=None,
    push_endpoint_source=None,
    opaque_data_source=None,
    persistent=False,
    time_to_live=None,
    max_retries=None,
    retry_sleep_duration=None,
    policy=None,
    verify_ssl=False,
    cloud_events=False,
    ca_location=None,
    amqp_exchange=None,
    ack_level=None,
    use_ssl=False,
    kafka_brokers=None,
    mechanism=None,
    include_secrets=False,
    profile="default",
):
    """Create an RGW notification topic."""
    return _invoke(
        rgw_topic_api.create_topic,
        name,
        daemon_name,
        owner,
        push_endpoint_source,
        opaque_data_source,
        persistent,
        time_to_live,
        max_retries,
        retry_sleep_duration,
        policy,
        verify_ssl,
        cloud_events,
        ca_location,
        amqp_exchange,
        ack_level,
        use_ssl,
        kafka_brokers,
        mechanism,
        include_secrets,
        profile,
    )


def list_topics(include_secrets=False, profile="default"):
    """List RGW notification topics."""
    return _invoke(rgw_topic_api.list_topics, include_secrets, profile)


def get_topic(key, include_secrets=False, profile="default"):
    """Return one RGW notification topic."""
    return _invoke(rgw_topic_api.get_topic, key, include_secrets, profile)


def delete_topic(key, confirm=False, profile="default"):
    """Delete an RGW notification topic after confirmation."""
    return _invoke(rgw_topic_api.delete_topic, key, confirm, profile)
