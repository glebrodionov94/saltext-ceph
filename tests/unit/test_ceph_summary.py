"""Dashboard summary controller tests."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_summary as execution
from saltext.ceph.utils.ceph import summary
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_summary as wrapper


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


def test_get_reads_summary_endpoint():
    client = Mock()
    client.request.return_value = APIResponse(
        200,
        {"health_status": "HEALTH_OK", "executing_tasks": [], "finished_tasks": []},
    )
    assert summary.get(client).data["health_status"] == "HEALTH_OK"
    client.request.assert_called_once_with("GET", "/api/summary", api_version="1.0")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"health_status": None, "executing_tasks": [], "finished_tasks": []},
        {"health_status": "HEALTH_OK", "executing_tasks": {}, "finished_tasks": []},
        {"health_status": "HEALTH_OK", "executing_tasks": [], "finished_tasks": {}},
    ],
)
def test_get_rejects_invalid_response(payload):
    client = Mock()
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        summary.get(client)
