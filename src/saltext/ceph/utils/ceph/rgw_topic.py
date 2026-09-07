"""Current Ceph Dashboard public RGW topic controller operations."""

from saltext.ceph.utils.ceph import rgw_common as common

API_VERSION = "1.0"
RESOURCE_PATH = "/api/rgw/topic"


def create_topic(
    client,
    name,
    daemon_name=None,
    owner=None,
    push_endpoint=None,
    opaque_data=None,
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
):
    """Create a current-only RGW notification topic."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    data = common.params(
        name=common.name(name, "name"),
        daemon_name=common.optional_text(daemon_name, "daemon_name"),
        owner=common.optional_text(owner, "owner"),
        push_endpoint=common.optional_text(push_endpoint, "push_endpoint"),
        opaque_data=common.optional_text(opaque_data, "opaque_data"),
        persistent=common.boolean(persistent, "persistent"),
        time_to_live=common.optional_text(time_to_live, "time_to_live"),
        max_retries=common.optional_text(max_retries, "max_retries"),
        retry_sleep_duration=common.optional_text(retry_sleep_duration, "retry_sleep_duration"),
        policy=common.optional_text(policy, "policy", max_length=1024 * 1024),
        verify_ssl=common.boolean(verify_ssl, "verify_ssl"),
        cloud_events=common.boolean(cloud_events, "cloud_events"),
        ca_location=common.optional_text(ca_location, "ca_location"),
        amqp_exchange=common.optional_text(amqp_exchange, "amqp_exchange"),
        ack_level=common.optional_text(ack_level, "ack_level"),
        use_ssl=common.boolean(use_ssl, "use_ssl"),
        kafka_brokers=common.optional_text(kafka_brokers, "kafka_brokers"),
        mechanism=common.optional_text(mechanism, "mechanism"),
    )
    response = client.request("POST", RESOURCE_PATH, api_version=API_VERSION, data=data)
    return common.safe_response(response, "RGW topic creation", include_secrets=include_secrets)


def list_topics(client, include_secrets=False):
    """List current-only RGW topics with endpoints redacted by default."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION)
    return common.safe_response(
        response,
        "RGW topic list",
        shape="mapping_list",
        include_secrets=include_secrets,
    )


def get_topic(client, key, include_secrets=False):
    """Return one current-only topic with endpoint data redacted by default."""
    include_secrets = common.boolean(include_secrets, "include_secrets")
    response = client.request(
        "GET",
        f"{RESOURCE_PATH}/{common.segment(key, 'key')}",
        api_version=API_VERSION,
    )
    return common.safe_response(
        response, "RGW topic", shape="mapping", include_secrets=include_secrets
    )


def delete_topic(client, key, confirm=False):
    """Delete a current-only RGW topic after explicit confirmation."""
    common.confirm(confirm)
    response = client.request(
        "DELETE",
        f"{RESOURCE_PATH}/{common.segment(key, 'key')}",
        api_version=API_VERSION,
    )
    return common.safe_response(response, "RGW topic deletion")
