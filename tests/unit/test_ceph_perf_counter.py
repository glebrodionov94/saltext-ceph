"""Dashboard performance-counter controller tests."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_perf_counter as execution
from saltext.ceph.utils.ceph import perf_counter
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_perf_counter as wrapper


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


def test_list_reads_all_unlabeled_counters():
    client = Mock()
    client.request.return_value = APIResponse(200, {"mon.a": {"counter": {"value": 1}}})
    assert perf_counter.list_(client).data["mon.a"]["counter"]["value"] == 1
    client.request.assert_called_once_with("GET", "/api/perf_counters", api_version="1.0")


@pytest.mark.parametrize("service_type", sorted(perf_counter.SERVICE_TYPES))
def test_get_supports_each_public_controller(service_type):
    client = Mock()
    client.request.return_value = APIResponse(200, {"counter": {"value": 1}})
    perf_counter.get(client, service_type, "daemon.1")
    client.request.assert_called_once_with(
        "GET",
        f"/api/perf_counters/{service_type}/daemon.1",
        api_version="1.0",
    )


def test_get_quotes_service_id():
    client = Mock()
    client.request.return_value = APIResponse(200, {})
    perf_counter.get(client, "rgw", "realm:zone@host")
    assert client.request.call_args.args[1].endswith("realm%3Azone%40host")


@pytest.mark.parametrize(
    "service_type,service_id",
    [("invalid", "a"), ("osd", ""), ("osd", "../1"), ("osd", 1), ("osd", "a" * 257)],
)
def test_get_rejects_invalid_path_values(service_type, service_id):
    client = Mock()
    with pytest.raises(ConfigurationError):
        perf_counter.get(client, service_type, service_id)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "function,args", [(perf_counter.list_, ()), (perf_counter.get, ("osd", "1"))]
)
def test_operations_reject_non_mapping_response(function, args):
    client = Mock()
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        function(client, *args)
