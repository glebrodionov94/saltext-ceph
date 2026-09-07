"""Grafana controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_grafana as execution
from saltext.ceph.utils.ceph import grafana
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_grafana as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, None)
    return client


def test_wrapper_exports_execution_functions_with_matching_signatures():
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
        assert inspect.signature(getattr(wrapper, name)) == inspect.signature(
            getattr(execution, name)
        )


def test_url_uses_api_v1_and_requires_instance_string(client):
    client.request.return_value = APIResponse(200, {"instance": "https://grafana.example"})
    result = grafana.url(client)
    assert result.data["instance"] == "https://grafana.example"
    client.request.assert_called_once_with("GET", "/api/grafana/url", api_version="1.0")


@pytest.mark.parametrize("payload", [None, [], {}, {"instance": None}])
def test_url_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        grafana.url(client)


def test_validate_dashboard_returns_grafana_http_status(client):
    client.request.return_value = APIResponse(200, 404)
    result = grafana.validate_dashboard(client, "ceph-cluster")
    assert result.data == 404
    client.request.assert_called_once_with(
        "GET", "/api/grafana/validation/ceph-cluster", api_version="1.0"
    )


@pytest.mark.parametrize("dashboard_uid", ["", "bad/uid", "bad uid", 42, "x" * 257])
def test_validate_dashboard_rejects_invalid_uid_before_http(client, dashboard_uid):
    with pytest.raises(ConfigurationError):
        grafana.validate_dashboard(client, dashboard_uid)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, True, "200", 99, 600, {}])
def test_validate_dashboard_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        grafana.validate_dashboard(client, "ceph-cluster")


def test_push_dashboards_uses_api_v1(client):
    client.request.return_value = APIResponse(201, {"success": True})
    result = grafana.push_dashboards(client)
    assert result.data == {"success": True}
    client.request.assert_called_once_with(
        "POST", "/api/grafana/dashboards", api_version="1.0", data={}
    )


@pytest.mark.parametrize("payload", [None, [], {}, {"success": 1}])
def test_push_dashboards_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(201, payload)
    with pytest.raises(ProtocolError):
        grafana.push_dashboards(client)
