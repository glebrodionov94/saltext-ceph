"""Exercise the HTTP contract without contacting a Ceph cluster."""

import json
from unittest.mock import Mock

import pytest
import requests

from saltext.ceph.utils.ceph.client import CephClient
from saltext.ceph.utils.ceph.config import ConnectionConfig
from saltext.ceph.utils.ceph.errors import APIError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.utils.ceph.errors import TransportError


def response(status=200, data=None, headers=None, content=None):
    """Use real Requests responses to cover decoding and header behavior."""
    result = requests.Response()
    result.status_code = status
    result.headers.update({"Content-Type": "application/vnd.ceph.api.v1.0+json"})
    result.headers.update(headers or {})
    result._content = json.dumps(data).encode() if content is None else content
    result._content_consumed = True
    return result


@pytest.fixture
def transport(monkeypatch):
    """Replace only the network boundary, retaining the actual session."""
    mocked = Mock()
    monkeypatch.setattr(requests.Session, "request", mocked)
    return mocked


@pytest.fixture
def client():
    instance = CephClient(ConnectionConfig(url="https://ceph.example/dashboard/", token="secret"))
    yield instance
    instance.close()


def credentials_client():
    """Return a password-authenticated client."""
    return CephClient(
        ConnectionConfig(url="https://ceph.example", username="salt", password="secret")
    )


def test_request_contract(client, transport):
    transport.return_value = response(
        data=[{"hostname": "node1"}],
        headers={"X-Total-Count": "11", "Set-Cookie": "secret", "Authorization": "secret"},
    )
    result = client.request("get", "/api/host", api_version="1.3", params={"offset": 5})
    args, kwargs = transport.call_args
    assert args == ("GET", "https://ceph.example/dashboard/api/host")
    assert kwargs["headers"] == {
        "Accept": "application/vnd.ceph.api.v1.3+json",
        "Authorization": "Bearer secret",
    }
    assert kwargs["timeout"] == (5.0, 30.0)
    assert kwargs["verify"] is True
    assert kwargs["allow_redirects"] is False
    assert kwargs["params"] == {"offset": 5}
    assert result.as_dict() == {
        "status": 200,
        "data": [{"hostname": "node1"}],
        "headers": {"content-type": "application/vnd.ceph.api.v1.0+json", "x-total-count": "11"},
    }
    assert "node1" not in repr(result)


def test_login_reuse_and_refresh(transport):
    client = credentials_client()
    transport.side_effect = [
        response(201, {"token": "first"}),
        response(data={"health": "ok"}),
        response(401),
        response(201, {"token": "second"}),
        response(data=[]),
    ]
    try:
        client.request("GET", "/api/health/minimal", api_version="1.0")
        client.request("GET", "/api/service", api_version="2.0")
        calls = transport.call_args_list
        assert calls[0].args == ("POST", "https://ceph.example/api/auth")
        assert calls[0].kwargs["json"] == {"username": "salt", "password": "secret"}
        assert "Authorization" not in calls[0].kwargs["headers"]
        assert calls[2].kwargs["headers"]["Authorization"] == "Bearer first"
        assert calls[4].kwargs["headers"]["Authorization"] == "Bearer second"
        assert calls[4].kwargs["headers"]["Accept"] == "application/vnd.ceph.api.v2.0+json"
    finally:
        client.close()


def test_explicit_login_hides_token_and_sends_optional_ttl(transport):
    client = credentials_client()
    transport.return_value = response(
        201,
        {
            "token": "private-jwt",
            "username": "salt",
            "permissions": {"hosts": ["read"]},
            "pwdUpdateRequired": False,
        },
    )
    try:
        result = client.login(ttl=4)
        assert result.data == {
            "username": "salt",
            "permissions": {"hosts": ["read"]},
            "pwdUpdateRequired": False,
        }
        assert "private-jwt" not in repr(result)
        assert transport.call_args.kwargs["json"] == {
            "username": "salt",
            "password": "secret",
            "ttl": 4,
        }
    finally:
        client.close()


@pytest.mark.parametrize("ttl", [0, -1, 1.5, True, "1"])
def test_login_validates_ttl_before_transport(ttl, transport):
    client = credentials_client()
    try:
        with pytest.raises(ConfigurationError, match="ttl"):
            client.login(ttl=ttl)
        transport.assert_not_called()
    finally:
        client.close()


def test_static_token_profile_cannot_login(client, transport):
    with pytest.raises(ConfigurationError, match="username/password"):
        client.login()
    transport.assert_not_called()


def test_auth_check_uses_controller_contract_without_returning_token(client, transport):
    transport.return_value = response(
        201,
        {"username": "salt", "permissions": {"hosts": ["read"]}, "sso": False},
    )
    result = client.check()
    assert result.data["username"] == "salt"
    assert result.data["authenticated"] is True
    assert "token" not in result.data
    assert transport.call_args.args == ("POST", "https://ceph.example/dashboard/api/auth/check")
    assert transport.call_args.kwargs["params"] == {"token": "secret"}
    assert transport.call_args.kwargs["json"] == {}
    assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"


def test_logout_revokes_token_and_clears_local_identity(transport):
    client = credentials_client()
    transport.side_effect = [
        response(201, {"token": "private-jwt", "username": "salt"}),
        response(200, {"redirect_url": "#/login", "protocol": "local"}),
    ]
    try:
        client.login()
        result = client.logout()
        assert result.data == {"redirect_url": "#/login", "protocol": "local"}
        assert transport.call_args.args == ("POST", "https://ceph.example/api/auth/logout")
        assert transport.call_args.kwargs["json"] == {}
        assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer private-jwt"
        assert client._token is None  # pylint: disable=protected-access
        assert client._identity is None  # pylint: disable=protected-access
    finally:
        client.close()


def test_failed_logout_still_forgets_rejected_token(client, transport):
    transport.return_value = response(401, {"detail": "expired"})
    with pytest.raises(APIError):
        client.logout()
    assert client._token is None  # pylint: disable=protected-access


def test_transport_failure_during_logout_forgets_uncertain_token(client, transport):
    transport.side_effect = requests.Timeout("private-jwt")
    with pytest.raises(TransportError):
        client.logout()
    assert client._token is None  # pylint: disable=protected-access


def test_check_marks_controller_login_response_as_unauthenticated(client, transport):
    transport.return_value = response(201, {"login_url": "#/login", "cluster_status": "INSTALLED"})
    result = client.check()
    assert result.data == {
        "login_url": "#/login",
        "cluster_status": "INSTALLED",
        "authenticated": False,
    }


def test_refresh_is_bounded(transport):
    client = credentials_client()
    transport.side_effect = [
        response(201, {"token": "a"}),
        response(401),
        response(201, {"token": "b"}),
        response(401),
    ]
    try:
        with pytest.raises(APIError) as exc:
            client.request("GET", "/api/host", api_version="1.3")
        assert exc.value.status == 401
        assert transport.call_count == 4
    finally:
        client.close()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_write_401_is_not_replayed(method, transport):
    client = credentials_client()
    transport.side_effect = [response(201, {"token": "a"}), response(401)]
    try:
        with pytest.raises(APIError):
            client.request(method, "/api/service", api_version="1.0", data={"name": "test"})
        assert transport.call_count == 2
    finally:
        client.close()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 415, 429, 500, 503])
def test_errors_preserve_status_without_server_secrets(status, client, transport):
    transport.return_value = response(status, {"detail": "secret-password", "traceback": "private"})
    with pytest.raises(APIError) as exc:
        client.request("GET", "/api/host", api_version="1.3")
    assert exc.value.status == status
    assert "secret-password" not in str(exc.value)
    assert "private" not in str(exc.value)
    assert transport.call_count == 1


@pytest.mark.parametrize(
    "failure", [requests.Timeout, requests.ConnectionError, requests.exceptions.SSLError]
)
def test_transport_failures_are_sanitized_and_not_retried(failure, client, transport):
    transport.side_effect = failure("password=private")
    with pytest.raises(TransportError) as exc:
        client.request("POST", "/api/service", api_version="1.0", data={"name": "test"})
    assert "private" not in str(exc.value)
    assert transport.call_count == 1


def test_async_and_empty_responses(client, transport):
    task = {"name": "service/create", "metadata": {"service_name": "rgw.test"}}
    transport.side_effect = [response(202, task), response(204, content=b"")]
    result = client.request(
        "POST", "/api/service", api_version="1.0", data={"service_name": "rgw.test"}
    )
    assert result.status == 202
    assert result.data == task
    assert transport.call_count == 1
    result = client.request("DELETE", "/api/service/rgw.test", api_version="1.0")
    assert result.status == 204
    assert result.data is None


def test_expected_fsid_is_checked_once_before_writes(transport):
    client = CephClient(
        ConnectionConfig(
            url="https://ceph.example",
            token="secret",
            expected_fsid="f860ca2e-757d-48ce-b74a-87052cad563f",
        )
    )
    transport.side_effect = [
        response(data="f860ca2e-757d-48ce-b74a-87052cad563f"),
        response(202, {"name": "service/create"}),
        response(204, content=b""),
    ]
    try:
        client.request("POST", "/api/service", api_version="1.0", data={})
        client.request("DELETE", "/api/service/test", api_version="1.0")
        assert [call.args[0] for call in transport.call_args_list] == [
            "GET",
            "POST",
            "DELETE",
        ]
        assert transport.call_args_list[0].args[1].endswith("/api/health/get_cluster_fsid")
    finally:
        client.close()


def test_fsid_mismatch_refuses_write(transport):
    client = CephClient(
        ConnectionConfig(
            url="https://ceph.example",
            token="secret",
            expected_fsid="f860ca2e-757d-48ce-b74a-87052cad563f",
        )
    )
    transport.return_value = response(data="2518b021-1103-4459-a3c2-10a145c95f81")
    try:
        with pytest.raises(ConfigurationError, match="does not match"):
            client.request("PUT", "/api/osd/1/mark", api_version="1.0", data={})
        assert transport.call_count == 1
        assert transport.call_args.args[0] == "GET"
    finally:
        client.close()


@pytest.mark.parametrize("fsid", [None, "not-a-uuid"])
def test_invalid_fsid_response_refuses_write(transport, fsid):
    client = CephClient(
        ConnectionConfig(
            url="https://ceph.example",
            token="secret",
            expected_fsid="f860ca2e-757d-48ce-b74a-87052cad563f",
        )
    )
    transport.return_value = response(data=fsid)
    try:
        with pytest.raises(ProtocolError, match="FSID"):
            client.request("POST", "/api/service", api_version="1.0", data={})
        assert transport.call_count == 1
    finally:
        client.close()


@pytest.mark.parametrize(
    "reply",
    [
        response(307, headers={"Location": "https://untrusted.example"}),
        response(content=b"<html>login</html>", headers={"Content-Type": "text/html"}),
        response(content=b"broken-json"),
    ],
)
def test_unusable_responses(client, transport, reply):
    transport.return_value = reply
    with pytest.raises(ProtocolError):
        client.request("GET", "/api/host", api_version="1.3")
    assert transport.call_count == 1


@pytest.mark.parametrize(
    "data",
    [{}, {"token": ""}, {"token": "bad\r\nheader"}, {"token": "a", "pwdUpdateRequired": True}, []],
)
def test_login_requires_usable_token(data, transport):
    client = credentials_client()
    transport.return_value = response(201, data)
    try:
        with pytest.raises(ProtocolError):
            client.request("GET", "/api/host", api_version="1.3")
        assert transport.call_count == 1
    finally:
        client.close()


@pytest.mark.parametrize(
    "path",
    [
        "https://untrusted.example/api/host",
        "//untrusted.example/api/host",
        "/api/../auth",
        "/api/%2e%2e/auth",
        "/api/%252e%252e/auth",
        "/api/host?token=private",
        "/api/host#fragment",
        "/api/auth",
        "/api/auth/check",
        "/api/%61uth",
        "/api\\host",
        "/ui-api/host",
        "/api/ho\nst",
    ],
)
def test_invalid_paths_fail_before_authentication(path, transport):
    client = credentials_client()
    try:
        with pytest.raises(ConfigurationError):
            client.request("GET", path, api_version="1.0")
        transport.assert_not_called()
    finally:
        client.close()


@pytest.mark.parametrize("version", [1.0, None, "latest", "1.0\r\nsecret"])
def test_version_is_explicit_and_validated(version, client, transport):
    with pytest.raises(ConfigurationError):
        client.request("GET", "/api/host", api_version=version)
    transport.assert_not_called()


def test_closed_session_cannot_be_used(client, transport):
    client.close()
    with pytest.raises(ConfigurationError, match="closed"):
        client.request("GET", "/api/host", api_version="1.3")
    transport.assert_not_called()


@pytest.mark.parametrize("operation", ["login", "check", "logout"])
def test_closed_session_rejects_auth_operations(client, transport, operation):
    client.close()
    with pytest.raises(ConfigurationError, match="closed"):
        getattr(client, operation)()
    transport.assert_not_called()
