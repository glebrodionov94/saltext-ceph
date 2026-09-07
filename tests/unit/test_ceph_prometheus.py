"""Dashboard Prometheus controller tests."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_prometheus as execution
from saltext.ceph.utils.ceph import prometheus
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_prometheus as wrapper


@pytest.fixture
def client():
    result = Mock()
    result.request.return_value = APIResponse(200, {})
    return result


def test_wrapper_matches_execution_module():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    assert names == {
        name
        for name, function in inspect.getmembers(wrapper, inspect.isfunction)
        if not name.startswith("_")
    }
    for name in names:
        assert inspect.signature(getattr(execution, name)) == inspect.signature(
            getattr(wrapper, name)
        )


def test_alerts_filters_current_cluster_without_mutating_input(client):
    params = {"active": "true"}
    prometheus.alerts(client, params, cluster_filter=True)
    assert params == {"active": "true"}
    client.request.assert_called_once_with(
        "GET",
        "/api/prometheus",
        api_version="1.0",
        params={"active": "true", "cluster_filter": True},
    )


def test_rules_uses_query_parameters(client):
    prometheus.rules(client, {"type": ["alert", "record"]})
    client.request.assert_called_once_with(
        "GET",
        "/api/prometheus/rules",
        api_version="1.0",
        params={"type": ["alert", "record"]},
    )


def test_range_query_maps_expression_to_dashboard_params_name(client):
    prometheus.query_range(
        client,
        "rate(ceph_osd_op[5m])",
        start=1,
        end="2",
        step=15.0,
        params={"timeout": "5s"},
    )
    client.request.assert_called_once_with(
        "GET",
        "/api/prometheus/data",
        api_version="1.0",
        params={
            "timeout": "5s",
            "params": "rate(ceph_osd_op[5m])",
            "start": 1,
            "end": "2",
            "step": 15.0,
        },
    )


def test_instant_query_uses_current_ceph_route(client):
    prometheus.query(client, "up", {"time": 12})
    client.request.assert_called_once_with(
        "GET",
        "/api/prometheus/prometheus_query_data",
        api_version="1.0",
        params={"time": 12, "params": "up"},
    )


def test_silences_get_and_create(client):
    prometheus.silences(client, {"filter": "createdBy=gitops"})
    assert client.request.call_args.args[:2] == ("GET", "/api/prometheus/silences")
    client.reset_mock()
    silence = {"matchers": [], "comment": "maintenance"}
    prometheus.create_silence(client, silence)
    client.request.assert_called_once_with(
        "POST", "/api/prometheus/silence", api_version="1.0", data=silence
    )


def test_delete_silence_requires_confirmation(client):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        prometheus.delete_silence(client, "a1")
    client.request.assert_not_called()
    client.request.return_value = APIResponse(204, None)
    assert prometheus.delete_silence(client, "a1", confirm=True).status == 204
    client.request.assert_called_once_with(
        "DELETE", "/api/prometheus/silence/a1", api_version="1.0"
    )


def test_alert_groups_uses_current_ceph_route(client):
    prometheus.alert_groups(client, cluster_filter=True)
    client.request.assert_called_once_with(
        "GET",
        "/api/prometheus/alertgroup",
        api_version="1.0",
        params={"cluster_filter": True},
    )


@pytest.mark.parametrize(
    "from_,expected",
    [(None, {}), ("last", {"from": "last"}), (0, {"from": 0}), ("12", {"from": 12})],
)
def test_notifications_cursor(client, from_, expected):
    prometheus.notifications(client, from_)
    client.request.assert_called_once_with(
        "GET",
        "/api/prometheus/notifications",
        api_version="1.0",
        params=expected,
    )


def test_set_remote_write_validates_and_sends_body(client):
    client.request.return_value = APIResponse(202, {"name": "prometheus/remote-write"})
    result = prometheus.set_remote_write(
        client,
        "https://metrics.example/api/v1/write",
        ["ceph_health_status", "ceph_pool:usage"],
    )
    assert result.status == 202
    client.request.assert_called_once_with(
        "PUT",
        "/api/prometheus/set_remote_write",
        api_version="1.0",
        data={
            "remote_write_url": "https://metrics.example/api/v1/write",
            "remote_write_allowed_metrics": ["ceph_health_status", "ceph_pool:usage"],
        },
    )


def test_remove_remote_write_requires_confirmation(client):
    url = "http://prometheus:9090/api/v1/write"
    with pytest.raises(ConfigurationError, match="confirm=True"):
        prometheus.remove_remote_write(client, url)
    client.request.assert_not_called()
    prometheus.remove_remote_write(client, url, confirm=True)
    client.request.assert_called_once_with(
        "PUT",
        "/api/prometheus/remove_remote_write",
        api_version="1.0",
        data={"url": url},
    )


@pytest.mark.parametrize(
    "function,args",
    [
        (prometheus.alerts, (None, "true")),
        (prometheus.alerts, ([], False)),
        (prometheus.rules, ({"bad key": "x"},)),
        (prometheus.rules, ({"filter": []},)),
        (prometheus.query_range, ("",)),
        (prometheus.query_range, ("up\x00",)),
        (prometheus.notifications, (-1,)),
        (prometheus.notifications, ("old",)),
        (prometheus.create_silence, ([],)),
        (prometheus.delete_silence, ("../bad", True)),
        (prometheus.set_remote_write, ("ftp://metrics", ["metric"])),
        (prometheus.set_remote_write, ("https://u:p@metrics/write", ["metric"])),
        (prometheus.set_remote_write, ("https://metrics/write?token=x", ["metric"])),
        (prometheus.set_remote_write, ("https://metrics/write", [])),
        (prometheus.set_remote_write, ("https://metrics/write", ["bad metric"])),
    ],
)
def test_invalid_arguments_fail_before_http(client, function, args):
    with pytest.raises(ConfigurationError):
        function(client, *args)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [object(), {"bad": object()}, float("nan")])
def test_invalid_server_json_is_a_protocol_error(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        prometheus.alerts(client)
