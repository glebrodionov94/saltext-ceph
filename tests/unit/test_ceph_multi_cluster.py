"""Current-only Dashboard multi-cluster adapter tests."""

import inspect
from copy import deepcopy
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_multi_cluster as execution
from saltext.ceph.utils.ceph import multi_cluster
from saltext.ceph.utils.ceph import multi_cluster_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_multi_cluster as wrapper


@pytest.fixture
def client():
    result = Mock()
    result.request.return_value = APIResponse(200, True)
    return result


def test_wrapper_exports_matching_public_signatures():
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


def test_connect_uses_public_route_and_complete_frontend_payload(client):
    result = multi_cluster.connect(
        client,
        "https://remote.example/dashboard/",
        "remote",
        "administrator",
        "private-password",
        "https://hub.example",
        ssl_verify=False,
        ttl=24,
    )
    assert result.data is True
    client.request.assert_called_once_with(
        "POST",
        "/api/multi-cluster/auth",
        api_version="1.0",
        data={
            "url": "https://remote.example/dashboard",
            "cluster_alias": "remote",
            "username": "administrator",
            "password": "private-password",
            "hub_url": "https://hub.example",
            "ssl_verify": False,
            "ssl_certificate": None,
            "ttl": 24,
        },
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example",
        "ftp://remote.example",
        "https://user:pass@remote.example",
        "https://remote.example/api",
        "https://remote.example/dashboard%2Fapi",
        "https://remote.example/path?query=1",
        "https://remote.example/%2e%2e/api",
    ],
)
def test_connect_rejects_unsafe_remote_urls_before_http(client, url):
    with pytest.raises(ConfigurationError):
        multi_cluster.connect(
            client,
            url,
            "remote",
            "administrator",
            "private-password",
            "https://hub.example",
            ssl_verify=False,
        )
    client.request.assert_not_called()


def test_connect_allows_explicit_plain_http_for_isolated_labs(client):
    multi_cluster.connect(
        client,
        "http://remote.example",
        "remote",
        "administrator",
        "private-password",
        "http://hub.example",
        ssl_verify=False,
        allow_http=True,
    )
    assert client.request.call_args.kwargs["data"]["url"] == "http://remote.example"


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"ssl_verify": True},
        {"ssl_certificate": "certificate"},
        {"ssl_verify": "true", "ssl_certificate": "certificate"},
        {"ttl": 0},
        {"ttl": True},
    ],
)
def test_connect_validates_tls_and_ttl_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        multi_cluster.connect(
            client,
            "https://remote.example",
            "remote",
            "administrator",
            "private-password",
            "https://hub.example",
            **kwargs,
        )
    client.request.assert_not_called()


def test_connect_accepts_explicit_remote_certificate(client):
    multi_cluster.connect(
        client,
        "https://remote.example",
        "remote",
        "administrator",
        "private-password",
        "https://hub.example",
        ssl_verify=True,
        ssl_certificate="-----BEGIN CERTIFICATE-----\nvalue",
    )
    assert client.request.call_args.kwargs["data"]["ssl_verify"] is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cluster_alias": "\ud800", "ssl_verify": False},
        {"ssl_verify": True, "ssl_certificate": "\ud800"},
    ],
)
def test_connect_rejects_invalid_unicode_before_http(client, kwargs):
    arguments = {
        "url": "https://remote.example",
        "cluster_alias": "remote",
        "username": "administrator",
        "password": "private-password",
        "hub_url": "https://hub.example",
    }
    arguments.update(kwargs)
    with pytest.raises(ConfigurationError):
        multi_cluster.connect(client, **arguments)
    client.request.assert_not_called()


def test_set_current_uses_nested_config_shape(client):
    client.request.return_value = APIResponse(200, {"current_user": "administrator"})
    result = multi_cluster.set_current(client, "https://remote.example", "administrator")
    assert result.data["current_user"] == "administrator"
    assert client.request.call_args.kwargs["data"] == {
        "config": {"url": "https://remote.example", "user": "administrator"}
    }


def test_reconnect_requires_exactly_one_credential(client):
    for password, token in ((None, None), ("password", "token")):
        with pytest.raises(ConfigurationError, match="exactly one"):
            multi_cluster.reconnect(
                client,
                "https://remote.example",
                "administrator",
                password=password,
                cluster_token=token,
            )
    client.request.assert_not_called()


def test_reconnect_redacts_an_echoed_token(client):
    client.request.return_value = APIResponse(200, {"cluster_token": "private"})
    result = multi_cluster.reconnect(
        client,
        "https://remote.example",
        "administrator",
        cluster_token="private",
        ssl_verify=False,
    )
    assert result.data == {"cluster_token": multi_cluster.REDACTED, "redacted": True}


def test_edit_maps_verify_parameter_and_redacts_returned_tokens(client):
    client.request.return_value = APIResponse(200, {"config": {"token": "private"}})
    result = multi_cluster.edit(
        client,
        "remote-fsid",
        "https://remote.example",
        "renamed",
        "administrator",
        ssl_verify=False,
    )
    assert client.request.call_args.kwargs["data"]["verify"] is False
    assert result.data["config"]["token"] == multi_cluster.REDACTED


@pytest.mark.parametrize("confirm", [False, None, 1, "true"])
def test_delete_requires_explicit_confirmation(client, confirm):
    with pytest.raises(ConfigurationError):
        multi_cluster.delete(client, "remote cluster", "admin@example", confirm=confirm)
    client.request.assert_not_called()


def test_delete_percent_encodes_both_route_identities(client):
    client.request.return_value = APIResponse(200, {})
    multi_cluster.delete(client, "remote cluster", "admin@example", confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        "/api/multi-cluster/delete_cluster/remote%20cluster/admin%40example",
        api_version="1.0",
    )


def test_get_config_recursively_redacts_tokens_by_default(client):
    payload = {
        "current_user": "administrator",
        "config": {
            "fsid": [
                {
                    "token": "private-jwt",
                    "prometheus_access_info": {"user": "prom", "password": "private"},
                }
            ]
        },
    }
    original = deepcopy(payload)
    client.request.return_value = APIResponse(200, payload)
    result = multi_cluster.get_config(client)
    entry = result.data["config"]["fsid"][0]
    assert entry["token"] == multi_cluster.REDACTED
    assert entry["prometheus_access_info"]["password"] == multi_cluster.REDACTED
    assert result.data["redacted"] is True
    assert payload == original
    assert multi_cluster.get_config(client, include_secrets=True).data == payload


@pytest.mark.parametrize("include_secrets", [None, 1, "true"])
def test_get_config_requires_boolean_secret_opt_in(client, include_secrets):
    client.request.return_value = APIResponse(200, {})
    with pytest.raises(ConfigurationError):
        multi_cluster.get_config(client, include_secrets=include_secrets)


def test_read_helpers_use_expected_routes_and_validate_shapes(client):
    client.request.side_effect = [
        APIResponse(200, {"remote": {"status": 0}}),
        APIResponse(200, {"security_enabled": True, "mgmt_gw_enabled": False}),
        APIResponse(200, "https://prometheus.example"),
    ]
    assert multi_cluster.token_status(client).data["remote"]["status"] == 0
    assert multi_cluster.security_config(client).data["security_enabled"] is True
    assert multi_cluster.prometheus_api_url(client).data == "https://prometheus.example"
    assert [call.args[1] for call in client.request.call_args_list] == [
        "/api/multi-cluster/check_token_status",
        "/api/multi-cluster/security_config",
        "/api/multi-cluster/get_prometheus_api_url",
    ]


@pytest.mark.parametrize(
    "function,payload",
    [
        (multi_cluster.token_status, []),
        (multi_cluster.security_config, []),
        (multi_cluster.prometheus_api_url, {}),
    ],
)
def test_read_helpers_reject_invalid_shapes(client, function, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        function(client)


def test_salt_api_reads_password_token_and_certificate_files(client, tmp_path, monkeypatch):
    password = tmp_path / "password"
    token = tmp_path / "token"
    certificate = tmp_path / "certificate"
    password.write_text("private-password\n", encoding="utf-8")
    token.write_text("private-token\n", encoding="utf-8")
    certificate.write_text("-----BEGIN CERTIFICATE-----\nvalue", encoding="utf-8")
    monkeypatch.setattr(multi_cluster_api, "_client", lambda *_args: client)
    client.request.return_value = APIResponse(200, True)

    multi_cluster_api.connect(
        {},
        {},
        {},
        "https://remote.example",
        "remote",
        "administrator",
        str(password),
        "https://hub.example",
        ssl_verify=True,
        ssl_certificate_source=str(certificate),
    )
    assert client.request.call_args.kwargs["data"]["password"] == "private-password"
    assert "BEGIN CERTIFICATE" in client.request.call_args.kwargs["data"]["ssl_certificate"]

    multi_cluster_api.reconnect(
        {},
        {},
        {},
        "https://remote.example",
        "administrator",
        cluster_token_source=str(token),
        ssl_verify=False,
    )
    assert client.request.call_args.kwargs["data"]["cluster_token"] == "private-token"
