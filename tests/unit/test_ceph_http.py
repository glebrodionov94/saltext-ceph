"""Exercise real HTTP serialization against a loopback Dashboard stub."""

import json
import threading
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

import pytest

from saltext.ceph.utils.ceph.client import CephClient
from saltext.ceph.utils.ceph.config import ConnectionConfig
from saltext.ceph.utils.ceph.errors import ProtocolError


@pytest.fixture
def dashboard():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):  # pylint: disable=invalid-name
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size)) if size else None
            calls.append((self.command, self.path, dict(self.headers), body))
            if self.path.startswith("/prefix/api/auth/check"):
                payload = {"username": "salt", "permissions": {"hosts": ["read"]}}
                status = 201
            elif self.path == "/prefix/api/auth/logout":
                payload = {"redirect_url": "#/login", "protocol": "local"}
                status = 200
            else:
                payload = {"token": "stub-jwt", "username": "salt"}
                status = 201
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "token=should-not-be-reused; Path=/")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def do_GET(self):  # pylint: disable=invalid-name
            calls.append((self.command, self.path, dict(self.headers), None))
            if self.path.endswith("/redirect"):
                self.send_response(307)
                self.send_header("Location", "/prefix/api/health/minimal")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.ceph.api.v1.0+json")
            self.end_headers()
            self.wfile.write(b'{"health": {"status": "HEALTH_OK"}}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/prefix", calls
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_http_authentication_and_prefix(dashboard, monkeypatch, tmp_path):
    url, calls = dashboard
    netrc = tmp_path / "netrc"
    netrc.write_text("machine 127.0.0.1 login wrong password wrong\n")
    monkeypatch.setenv("NETRC", str(netrc))
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    client = CephClient(
        ConnectionConfig(url=url, username="salt", password="stub-password", allow_http=True)
    )
    try:
        result = client.request(
            "GET", "/api/health/minimal", api_version="1.0", params={"search": "a b&c"}
        )
        assert result.data == {"health": {"status": "HEALTH_OK"}}
        assert calls[0][1] == "/prefix/api/auth"
        assert calls[0][2]["Content-Type"] == "application/json"
        assert "Authorization" not in calls[0][2]
        assert calls[0][3] == {"username": "salt", "password": "stub-password"}
        assert calls[1][1] == "/prefix/api/health/minimal?search=a+b%26c"
        assert calls[1][2]["Authorization"] == "Bearer stub-jwt"
        assert "Cookie" not in calls[1][2]
    finally:
        client.close()


def test_http_redirect_is_not_followed(dashboard):
    url, calls = dashboard
    client = CephClient(ConnectionConfig(url=url, token="stub-jwt", allow_http=True))
    try:
        with pytest.raises(ProtocolError, match="redirect"):
            client.request("GET", "/api/redirect", api_version="1.0")
        assert len(calls) == 1
    finally:
        client.close()


def test_http_auth_controller_lifecycle(dashboard):
    url, calls = dashboard
    client = CephClient(
        ConnectionConfig(
            url=url,
            username="salt",
            password="stub-password",
            allow_http=True,
        )
    )
    try:
        login = client.login()
        checked = client.check()
        logout = client.logout()
        assert login.data == {"username": "salt"}
        assert checked.data == {
            "username": "salt",
            "permissions": {"hosts": ["read"]},
            "authenticated": True,
        }
        assert logout.data == {"redirect_url": "#/login", "protocol": "local"}
        assert calls[1][1] == "/prefix/api/auth/check?token=stub-jwt"
        assert calls[1][2]["Authorization"] == "Bearer stub-jwt"
        assert calls[2][1] == "/prefix/api/auth/logout"
        assert calls[2][2]["Authorization"] == "Bearer stub-jwt"
        assert all("Cookie" not in call[2] for call in calls)
    finally:
        client.close()
