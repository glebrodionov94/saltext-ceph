"""Transport exceptions shared by all Ceph loaders.

Exceptions intentionally omit URLs, credentials, request bodies and server error
bodies. Dashboard errors can echo secrets or include server tracebacks.
"""


class CephError(Exception):
    """Base exception for the API client."""


class ConfigurationError(CephError):
    """Invalid connection settings or request arguments."""


class TransportError(CephError):
    """No usable HTTP response; a submitted mutation may have taken effect."""


class ProtocolError(CephError):
    """The endpoint did not return the expected JSON protocol."""


class TaskTimeoutError(CephError):
    """A Dashboard asynchronous task did not finish before the deadline."""


class TaskFailedError(CephError):
    """A Dashboard asynchronous task completed unsuccessfully."""


class APIError(CephError):
    """An HTTP error with a machine-readable ``status`` attribute."""

    def __init__(self, status):
        self.status = status
        explanation = {
            400: "invalid request",
            401: "authentication failed or token expired",
            403: "permission denied",
            404: "resource or endpoint not found",
            409: "resource conflict",
            415: "API version or media type unsupported",
            429: "rate limit exceeded",
            503: "service unavailable",
        }.get(status, "request failed")
        super().__init__(f"Ceph API HTTP {status}: {explanation}.")
