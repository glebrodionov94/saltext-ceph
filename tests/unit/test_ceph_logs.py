"""Dashboard log controller tests."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_logs as execution
from saltext.ceph.utils.ceph import logs
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_logs as wrapper


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


def test_all_reads_bounded_dashboard_buffers():
    client = Mock()
    client.request.return_value = APIResponse(
        200,
        {"clog": [{"message": "healthy"}], "audit_log": []},
    )
    result = logs.all_(client)
    assert result.data["clog"][0]["message"] == "healthy"
    client.request.assert_called_once_with("GET", "/api/logs/all", api_version="1.0")


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"clog": [], "audit_log": None}, {"clog": {}, "audit_log": []}],
)
def test_all_rejects_invalid_response(payload):
    client = Mock()
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        logs.all_(client)
