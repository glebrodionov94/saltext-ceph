"""Current RGW topic Dashboard adapter tests."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rgw_topic as execution
from saltext.ceph.utils.ceph import rgw_topic
from saltext.ceph.utils.ceph import rgw_topic_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rgw_topic as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(201, {"name": "alerts"})
    return client


def test_wrapper_matches_execution_module():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    for name in names:
        assert inspect.signature(getattr(execution, name)) == inspect.signature(
            getattr(wrapper, name)
        )
        api_parameters = list(inspect.signature(getattr(rgw_topic_api, name)).parameters.values())
        assert inspect.signature(getattr(execution, name)) == inspect.Signature(api_parameters[3:])


def test_create_topic_preserves_exact_current_controller_body(client):
    rgw_topic.create_topic(
        client,
        "alerts",
        daemon_name="rgw.a",
        owner="alice",
        push_endpoint="https://user:pass@example.test/hook",
        opaque_data="opaque",
        persistent=True,
        time_to_live="3600",
        max_retries="7",
        retry_sleep_duration="5",
        policy='{"Statement":[]}',
        verify_ssl=True,
        cloud_events=True,
        ca_location="/etc/ceph/ca.pem",
        amqp_exchange="events",
        ack_level="broker",
        use_ssl=True,
        kafka_brokers="kafka:9093",
        mechanism="PLAIN",
    )
    call = client.request.call_args
    assert call.args == ("POST", "/api/rgw/topic")
    assert call.kwargs["api_version"] == "1.0"
    assert call.kwargs["data"] == {
        "name": "alerts",
        "daemon_name": "rgw.a",
        "owner": "alice",
        "push_endpoint": "https://user:pass@example.test/hook",
        "opaque_data": "opaque",
        "persistent": True,
        "time_to_live": "3600",
        "max_retries": "7",
        "retry_sleep_duration": "5",
        "policy": '{"Statement":[]}',
        "verify_ssl": True,
        "cloud_events": True,
        "ca_location": "/etc/ceph/ca.pem",
        "amqp_exchange": "events",
        "ack_level": "broker",
        "use_ssl": True,
        "kafka_brokers": "kafka:9093",
        "mechanism": "PLAIN",
    }


@pytest.mark.parametrize(
    "field,value",
    [("persistent", "true"), ("verify_ssl", 1), ("cloud_events", None), ("use_ssl", "false")],
)
def test_create_topic_rejects_non_boolean_flags(client, field, value):
    kwargs = {field: value}
    with pytest.raises(ConfigurationError):
        rgw_topic.create_topic(client, "alerts", **kwargs)
    client.request.assert_not_called()


def test_create_topic_rejects_non_boolean_secret_opt_in_before_request(client):
    with pytest.raises(ConfigurationError):
        rgw_topic.create_topic(client, "alerts", include_secrets="true")
    client.request.assert_not_called()


def test_list_topics_redacts_endpoints_and_opaque_data_by_default(client):
    client.request.return_value = APIResponse(
        200,
        [
            {
                "name": "alerts",
                "push_endpoint": "https://user:pass@example.test/hook",
                "opaque_data": "tenant-secret",
            }
        ],
    )
    result = rgw_topic.list_topics(client)
    assert result.data[0]["push_endpoint"] == "***********"
    assert result.data[0]["opaque_data"] == "***********"
    client.request.assert_called_once_with("GET", "/api/rgw/topic", api_version="1.0")


def test_topic_secret_opt_in_returns_detached_values(client):
    payload = {"name": "alerts", "push_endpoint": "amqps://user:pass@mq/vhost"}
    client.request.return_value = APIResponse(200, payload)
    result = rgw_topic.get_topic(client, "alice:alerts", include_secrets=True)
    assert result.data == payload
    assert result.data is not payload
    client.request.assert_called_once_with(
        "GET", "/api/rgw/topic/alice%3Aalerts", api_version="1.0"
    )


@pytest.mark.parametrize("payload", [None, [], "topic"])
def test_get_topic_rejects_non_mapping_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        rgw_topic.get_topic(client, "alice:alerts")


def test_delete_topic_requires_confirmation(client):
    with pytest.raises(ConfigurationError):
        rgw_topic.delete_topic(client, "alice:alerts")
    client.request.assert_not_called()


def test_delete_topic_encodes_key_and_preserves_empty_response(client):
    client.request.return_value = APIResponse(204, None)
    result = rgw_topic.delete_topic(client, "alice:alerts", confirm=True)
    assert result.status == 204
    client.request.assert_called_once_with(
        "DELETE", "/api/rgw/topic/alice%3Aalerts", api_version="1.0"
    )


def test_topic_api_reads_private_endpoint_fields_from_files(client, monkeypatch, tmp_path):
    endpoint_source = tmp_path / "endpoint"
    opaque_source = tmp_path / "opaque"
    endpoint_source.write_text("https://user:pass@example.test/hook\n", encoding="utf-8")
    opaque_source.write_text("private-metadata\n", encoding="utf-8")
    client.request.return_value = APIResponse(
        201,
        {
            "name": "alerts",
            "push_endpoint": "https://user:pass@example.test/hook",
            "opaque_data": "private-metadata",
        },
    )
    monkeypatch.setattr(rgw_topic_api.ceph, "get_client", lambda *_: client)

    result = rgw_topic_api.create_topic(
        {},
        {},
        {},
        "alerts",
        push_endpoint_source=str(endpoint_source),
        opaque_data_source=str(opaque_source),
    )

    data = client.request.call_args.kwargs["data"]
    assert data["push_endpoint"] == "https://user:pass@example.test/hook"
    assert data["opaque_data"] == "private-metadata"
    assert result["data"]["push_endpoint"] == "***********"
    assert result["data"]["opaque_data"] == "***********"
    parameters = inspect.signature(execution.create_topic).parameters
    assert "push_endpoint" not in parameters
    assert "opaque_data" not in parameters
