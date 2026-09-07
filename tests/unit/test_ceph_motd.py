"""Current Dashboard MOTD plugin operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_motd as execution
from saltext.ceph.utils.ceph import motd
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_motd as wrapper


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


@pytest.mark.parametrize("expires", ["0", "30s", "2h", "10d", "4w", "-5m"])
def test_create_validates_and_sends_current_api_payload(client, expires):
    client.request.return_value = APIResponse(201, {})

    result = motd.create(client, "warning", expires, "Maintenance\nstarts soon")

    assert result.data == {}
    client.request.assert_called_once_with(
        "POST",
        "/api/motd",
        api_version="1.0",
        data={
            "severity": "warning",
            "expires": expires,
            "message": "Maintenance\nstarts soon",
        },
    )


@pytest.mark.parametrize("severity", [None, "", "INFO", "critical", 1, []])
def test_create_rejects_invalid_severity_before_request(client, severity):
    with pytest.raises(ConfigurationError, match="severity"):
        motd.create(client, severity, "2h", "message")
    client.request.assert_not_called()


@pytest.mark.parametrize("expires", [None, 2, "", "2", "0s", "2y", "2h junk"])
def test_create_rejects_invalid_expiry_before_request(client, expires):
    with pytest.raises(ConfigurationError, match="expires"):
        motd.create(client, "info", expires, "message")
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "message",
    [None, "", "bad\x00message", "\ud800", "x" * 65537],
    ids=("none", "empty", "nul", "surrogate", "too-long"),
)
def test_create_rejects_invalid_message_before_request(client, message):
    with pytest.raises(ConfigurationError, match="message"):
        motd.create(client, "info", "2h", message)
    client.request.assert_not_called()


@pytest.mark.parametrize("confirm", [False, None, 1, "true"])
def test_clear_requires_exact_confirmation_before_request(client, confirm):
    with pytest.raises(ConfigurationError, match="confirm"):
        motd.clear(client, confirm)
    client.request.assert_not_called()


@pytest.mark.parametrize("response", [APIResponse(204, None), APIResponse(202, {})])
def test_clear_uses_current_api_route(client, response):
    client.request.return_value = response

    result = motd.clear(client, confirm=True)

    assert result.status == response.status
    assert result.data == response.data
    client.request.assert_called_once_with("DELETE", "/api/motd/clear", api_version="1.0")


@pytest.mark.parametrize("operation", ["create", "clear"])
def test_mutations_reject_unexpected_response_shape(client, operation):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        if operation == "create":
            motd.create(client, "info", "2h", "message")
        else:
            motd.clear(client, confirm=True)
