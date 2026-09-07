"""Small synchronous client for the Ceph Dashboard REST API.

No resource reconciliation or OpenAPI code generation takes place here. Each
request supplies its operation's API version explicitly. A client belongs to a
single connection profile and must not be shared between threads.
"""

import re
import uuid
from dataclasses import dataclass
from dataclasses import field
from urllib.parse import unquote

import requests

from saltext.ceph.utils.ceph.config import validate_path
from saltext.ceph.utils.ceph.errors import APIError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.utils.ceph.errors import TransportError


@dataclass(frozen=True)
class APIResponse:
    """JSON response preserving HTTP status, task data and pagination headers.

    ``202`` means accepted, not converged. Only selected non-authentication
    headers are exposed; JSON data may itself contain sensitive resource values.
    """

    status: int
    data: object = field(repr=False)
    headers: dict = field(default_factory=dict, repr=False)

    def as_dict(self):
        """Return a Salt-serializable envelope."""
        return {"status": self.status, "data": self.data, "headers": dict(self.headers)}


class CephClient:
    """Authenticated HTTP session created from a ``ConnectionConfig``.

    JWTs remain in process memory. A credentials-based GET/HEAD can reauthenticate
    once on 401; writes, network failures and other HTTP errors are never retried.
    Environment proxies and netrc authentication are disabled for this session.
    """

    def __init__(self, config):
        self.config = config
        self._token = config.token
        self._identity = None
        self._session = requests.Session()
        self._session.trust_env = False
        self._closed = False
        self._fsid_verified = False

    def close(self):
        """Release the local session and token; this does not revoke a server JWT."""
        self._token = None
        self._identity = None
        self._session.cookies.clear()
        self._session.close()
        self._closed = True

    @property
    def closed(self):
        """Whether this session has been closed."""
        return self._closed

    def _send(self, method, path, api_version, *, params=None, data=None, token=None):
        headers = {"Accept": f"application/vnd.ceph.api.v{api_version}+json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        try:
            return self._session.request(
                method,
                self.config.url + path,
                headers=headers,
                params=params,
                json=data,
                verify=self.config.verify,
                timeout=(self.config.connect_timeout, self.config.read_timeout),
                allow_redirects=False,
            )
        except requests.exceptions.SSLError:
            raise TransportError("Ceph API TLS verification or handshake failed.") from None
        except requests.exceptions.Timeout:
            raise TransportError(
                "Ceph API request timed out; a submitted change may have taken effect."
            ) from None
        except (requests.exceptions.RequestException, OSError):
            raise TransportError(
                "Ceph API connection failed; a submitted change may have taken effect."
            ) from None
        finally:
            # Dashboard also issues cookies. Bearer auth is the sole session identity.
            self._session.cookies.clear()

    @staticmethod
    def _decode(response, method):
        if 300 <= response.status_code < 400:
            raise ProtocolError("Ceph API redirect refused; configure the active Dashboard URL.")
        if not 200 <= response.status_code < 300:
            raise APIError(response.status_code)
        data = None
        if response.status_code != 204 and method != "HEAD" and response.content:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type != "application/json" and not (
                content_type.startswith("application/") and content_type.endswith("+json")
            ):
                raise ProtocolError("Ceph API returned a non-JSON response.")
            try:
                data = response.json()
            except ValueError:
                raise ProtocolError("Ceph API returned invalid JSON.") from None
        headers = {
            name.lower(): value
            for name, value in response.headers.items()
            if name.lower() in ("content-type", "x-total-count")
        }
        return APIResponse(response.status_code, data, headers)

    @staticmethod
    def _public_identity(data):
        """Strip authentication material before returning session metadata."""
        if not isinstance(data, dict):
            raise ProtocolError("Ceph authentication returned invalid session metadata.")
        return {key: value for key, value in data.items() if key != "token"}

    def _login(self, ttl=None):
        if self.config.username is None:
            raise APIError(401)
        if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0):
            raise ConfigurationError("ttl must be a positive integer number of hours.")
        payload = {"username": self.config.username, "password": self.config.password}
        if ttl is not None:
            payload["ttl"] = ttl
        response = self._send(
            "POST",
            "/api/auth",
            "1.0",
            data=payload,
        )
        try:
            result = self._decode(response, "POST")
        finally:
            response.close()
        token = result.data.get("token") if isinstance(result.data, dict) else None
        if (
            result.status not in (200, 201)
            or not isinstance(token, str)
            or not token
            or re.search(r"\s|[^\x21-\x7e]", token)
        ):
            raise ProtocolError("Ceph authentication returned no usable token.")
        if result.data.get("pwdUpdateRequired"):
            raise ProtocolError("Ceph account requires a password update before API use.")
        self._token = token
        self._identity = self._public_identity(result.data)
        return APIResponse(result.status, dict(self._identity), result.headers)

    def login(self, ttl=None):
        """Authenticate with profile credentials and return metadata without JWT.

        ``ttl`` is supported by newer Ceph releases and is omitted by default for
        compatibility with Reef. Static-token profiles cannot call this endpoint.
        """
        if self._closed:
            raise ConfigurationError("Ceph client is closed.")
        if self.config.username is None:
            raise ConfigurationError("login requires a username/password profile.")
        return self._login(ttl=ttl)

    def check(self):
        """Validate the current token through ``POST /api/auth/check``.

        Ceph defines the token as a query parameter. Deployments should therefore
        prevent query strings from being recorded in proxy and access logs.
        """
        if self._closed:
            raise ConfigurationError("Ceph client is closed.")
        if self._token is None:
            self._login()
        response = self._send(
            "POST", "/api/auth/check", "1.0", params={"token": self._token}, token=self._token
        )
        try:
            result = self._decode(response, "POST")
        finally:
            response.close()
        identity = self._public_identity(result.data)
        identity["authenticated"] = isinstance(identity.get("username"), str)
        return APIResponse(result.status, identity, result.headers)

    def logout(self):
        """Revoke the current JWT and clear all local session authentication."""
        if self._closed:
            raise ConfigurationError("Ceph client is closed.")
        if self._token is None:
            self._login()
        response = None
        try:
            response = self._send("POST", "/api/auth/logout", "1.0", token=self._token)
            return self._decode(response, "POST")
        finally:
            self._token = None
            self._identity = None
            if response is not None:
                response.close()

    def request(self, method, path, *, api_version, params=None, data=None):
        """Request an ``/api/...`` path and return an :class:`APIResponse`.

        Supply query parameters in ``params`` and JSON in ``data``. Authentication
        endpoints are private to this client to keep tokens out of Salt returns.
        No automatic pagination or task polling occurs at this transport layer.
        """
        if self._closed:
            raise ConfigurationError("Ceph client is closed.")
        if not isinstance(method, str) or method.upper() not in (
            "GET",
            "HEAD",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        ):
            raise ConfigurationError("Unsupported HTTP method.")
        method = method.upper()
        validate_path(path)
        decoded_path = unquote(path)
        if not decoded_path.startswith("/api/") or decoded_path.split("/")[2] == "auth":
            raise ConfigurationError("Use an /api/ resource path outside /api/auth.")
        if not isinstance(api_version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+", api_version):
            raise ConfigurationError("api_version must be a quoted major.minor string.")
        if self._token is None:
            self._login()
        if method in ("POST", "PUT", "PATCH", "DELETE") and self.config.expected_fsid:
            self._verify_fsid()
        response = self._send(
            method, path, api_version, params=params, data=data, token=self._token
        )
        if response.status_code == 401 and self.config.username is not None:
            self._token = None
            if method in ("GET", "HEAD"):
                response.close()
                self._login()
                response = self._send(
                    method, path, api_version, params=params, data=data, token=self._token
                )
        try:
            if response.status_code == 401 and self.config.username is not None:
                self._token = None
            return self._decode(response, method)
        finally:
            response.close()

    def _verify_fsid(self):
        """Verify the configured cluster identity once before the first write."""
        if self._fsid_verified:
            return
        result = self.request("GET", "/api/health/get_cluster_fsid", api_version="1.0")
        if not isinstance(result.data, str):
            raise ProtocolError("Ceph cluster FSID returned an unexpected response shape.")
        try:
            actual = str(uuid.UUID(result.data))
        except ValueError:
            raise ProtocolError("Ceph cluster FSID returned an invalid UUID.") from None
        if actual != self.config.expected_fsid:
            raise ConfigurationError("Ceph cluster FSID does not match expected_fsid.")
        self._fsid_verified = True
