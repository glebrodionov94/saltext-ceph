"""Dashboard settings operations and secret handling."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_settings as execution
from saltext.ceph.utils.ceph import settings
from saltext.ceph.utils.ceph import settings_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_settings as wrapper


@pytest.fixture
def client():
    return Mock()


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


def test_list_uses_comma_filter_and_redacts_secret_options(client):
    client.request.return_value = APIResponse(
        200,
        [
            {
                "name": "GRAFANA_API_PASSWORD",
                "default": "admin",
                "type": "str",
                "value": "private-password",
            },
            {
                "name": "REST_REQUESTS_TIMEOUT",
                "default": 45,
                "type": "int",
                "value": 60,
            },
        ],
    )
    result = settings.list_(client, ["grafana-api-password", "REST_REQUESTS_TIMEOUT"])
    assert result.data[0] == {
        "name": "GRAFANA_API_PASSWORD",
        "default": settings.REDACTED,
        "type": "str",
        "value": settings.REDACTED,
        "redacted": True,
    }
    assert result.data[1]["value"] == 60
    assert "private-password" not in repr(result.as_dict())
    client.request.assert_called_once_with(
        "GET",
        "/api/settings",
        api_version="1.0",
        params={"names": "GRAFANA_API_PASSWORD,REST_REQUESTS_TIMEOUT"},
    )


def test_list_redacts_nested_credential_fields(client):
    client.request.return_value = APIResponse(
        200,
        [
            {
                "name": "MULTICLUSTER_CONFIG",
                "default": {},
                "type": "dict,str",
                "value": {"remote": {"url": "https://ceph", "token": "private"}},
            }
        ],
    )
    result = settings.list_(client)
    assert result.data[0]["value"]["remote"]["token"] == settings.REDACTED
    assert result.data[0]["redacted"] is True
    assert "private" not in repr(result.as_dict())


def test_get_normalizes_name_and_redacts_by_requested_name(client):
    client.request.return_value = APIResponse(
        200,
        {
            "name": "unexpected",
            "default": "admin",
            "type": "str",
            "value": "private",
        },
    )
    result = settings.get(client, "grafana-api-password")
    assert result.data["value"] == settings.REDACTED
    client.request.assert_called_once_with(
        "GET", "/api/settings/GRAFANA_API_PASSWORD", api_version="1.0"
    )


def test_set_delete_and_bulk_set_discard_values_from_returns(client):
    client.request.side_effect = [
        APIResponse(200, {"value": "private"}),
        APIResponse(204, None),
        APIResponse(200, {"GRAFANA_API_PASSWORD": "private"}),
    ]
    assert settings.set_(client, "grafana-api-password", "private").data == {
        "name": "GRAFANA_API_PASSWORD"
    }
    client.request.assert_called_with(
        "PUT",
        "/api/settings/GRAFANA_API_PASSWORD",
        api_version="1.0",
        data={"value": "private"},
    )
    assert settings.delete(client, "rest-requests-timeout").data == {
        "name": "REST_REQUESTS_TIMEOUT"
    }
    client.request.assert_called_with(
        "DELETE", "/api/settings/REST_REQUESTS_TIMEOUT", api_version="1.0"
    )
    result = settings.bulk_set(
        client, {"REST_REQUESTS_TIMEOUT": 60, "GRAFANA_API_PASSWORD": "private"}
    )
    assert result.data == {"names": ["REST_REQUESTS_TIMEOUT", "GRAFANA_API_PASSWORD"]}
    assert "private" not in repr(result.as_dict())
    client.request.assert_called_with(
        "PUT",
        "/api/settings",
        api_version="1.0",
        data={"REST_REQUESTS_TIMEOUT": 60, "GRAFANA_API_PASSWORD": "private"},
    )


@pytest.mark.parametrize("name", [None, "", "bad/name", "bad name", "_PRIVATE"])
def test_invalid_setting_names_fail_before_http(client, name):
    with pytest.raises(ConfigurationError):
        settings.get(client, name)
    client.request.assert_not_called()


@pytest.mark.parametrize("names", [[], "REST_REQUESTS_TIMEOUT", ["foo-bar", "FOO_BAR"], [1]])
def test_invalid_list_filters_fail_before_http(client, names):
    with pytest.raises(ConfigurationError):
        settings.list_(client, names)
    client.request.assert_not_called()


@pytest.mark.parametrize("value", [None, {1, 2}, float("nan"), "bad\x00value"])
def test_invalid_setting_values_fail_before_http(client, value):
    with pytest.raises(ConfigurationError):
        settings.set_(client, "REST_REQUESTS_TIMEOUT", value)
    client.request.assert_not_called()


@pytest.mark.parametrize("values", [None, {}, [], {"foo-bar": 1, "FOO_BAR": 2}])
def test_invalid_bulk_values_fail_before_http(client, values):
    with pytest.raises(ConfigurationError):
        settings.bulk_set(client, values)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, {}, ["bad"]])
def test_list_rejects_invalid_protocol_shape(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        settings.list_(client)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"name": "OPTION", "value": 1},
        {"name": "OPTION", "default": 1},
        {"name": "OPTION", "default": 1, "value": 2},
        {"name": "bad/name", "default": 1, "type": "int", "value": 2},
    ],
)
def test_get_rejects_invalid_protocol_shape(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        settings.get(client, "OPTION")


def test_api_requires_secret_source_and_returns_no_secret(tmp_path, monkeypatch):
    source = tmp_path / "grafana-password"
    source.write_text("private-password\n", encoding="utf-8")
    client = Mock()
    client.request.return_value = APIResponse(200, {"value": "private-password"})
    monkeypatch.setattr(settings_api, "_client", lambda *_args: client)
    result = settings_api.set_({}, {}, {}, "GRAFANA_API_PASSWORD", source=str(source))
    assert result["data"] == {"name": "GRAFANA_API_PASSWORD"}
    assert "private-password" not in repr(result)
    assert client.request.call_args.kwargs["data"] == {"value": "private-password"}


def test_api_rejects_secret_in_value_and_nonsecret_in_source(tmp_path):
    source = tmp_path / "value"
    source.write_text("60", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        settings_api.set_({}, {}, {}, "GRAFANA_API_PASSWORD", value="private")
    with pytest.raises(ConfigurationError):
        settings_api.set_({}, {}, {}, "REST_REQUESTS_TIMEOUT", source=str(source))


def test_api_bulk_set_routes_secret_files(tmp_path, monkeypatch):
    source = tmp_path / "grafana-password"
    source.write_text("private-password\n", encoding="utf-8")
    client = Mock()
    client.request.return_value = APIResponse(200, None)
    monkeypatch.setattr(settings_api, "_client", lambda *_args: client)
    result = settings_api.bulk_set(
        {},
        {},
        {},
        values={"rest-requests-timeout": 60},
        secret_sources={"grafana-api-password": str(source)},
    )
    assert result["data"] == {"names": ["REST_REQUESTS_TIMEOUT", "GRAFANA_API_PASSWORD"]}
    assert "private-password" not in repr(result)
    assert client.request.call_args.kwargs["data"] == {
        "REST_REQUESTS_TIMEOUT": 60,
        "GRAFANA_API_PASSWORD": "private-password",
    }
