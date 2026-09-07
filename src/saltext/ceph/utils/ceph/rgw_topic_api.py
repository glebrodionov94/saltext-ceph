"""Salt-facing composition for current-only public RGW topic operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph import rgw_topic


def _call(operation, opts, pillar, context, profile, *args, **kwargs):
    client = ceph.get_client(opts, pillar, context, profile)
    return operation(client, *args, **kwargs).as_dict()


def create_topic(
    opts,
    pillar,
    context,
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
    return _call(
        rgw_topic.create_topic,
        opts,
        pillar,
        context,
        profile,
        name,
        daemon_name,
        owner,
        common.secret_from_file(push_endpoint_source, "push_endpoint"),
        common.secret_from_file(opaque_data_source, "opaque_data"),
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
    )


def list_topics(opts, pillar, context, include_secrets=False, profile="default"):
    """List RGW notification topics."""
    return _call(
        rgw_topic.list_topics,
        opts,
        pillar,
        context,
        profile,
        include_secrets,
    )


def get_topic(opts, pillar, context, key, include_secrets=False, profile="default"):
    """Return one RGW notification topic."""
    return _call(
        rgw_topic.get_topic,
        opts,
        pillar,
        context,
        profile,
        key,
        include_secrets,
    )


def delete_topic(opts, pillar, context, key, confirm=False, profile="default"):
    """Delete an RGW notification topic after confirmation."""
    return _call(
        rgw_topic.delete_topic,
        opts,
        pillar,
        context,
        profile,
        key,
        confirm,
    )
