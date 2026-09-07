"""Dashboard monitor controller tests."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_monitor as execution
from saltext.ceph.utils.ceph import monitor
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_monitor as wrapper


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


def test_status_reads_monitor_endpoint():
    client = Mock()
    client.request.return_value = APIResponse(
        200,
        {"mon_status": {"quorum": [0]}, "in_quorum": [{"rank": 0}], "out_quorum": []},
    )
    result = monitor.status(client)
    assert result.data["mon_status"]["quorum"] == [0]
    client.request.assert_called_once_with("GET", "/api/monitor", api_version="1.0")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"mon_status": [], "in_quorum": [], "out_quorum": []},
        {"mon_status": {}, "in_quorum": {}, "out_quorum": []},
        {"mon_status": {}, "in_quorum": [], "out_quorum": {}},
    ],
)
def test_status_rejects_invalid_response(payload):
    client = Mock()
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        monitor.status(client)
