"""Manager module controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_mgr_module as execution
from saltext.ceph.utils.ceph import mgr_module
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_mgr_module as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, None)
    return client


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


def test_list_returns_module_mappings(client):
    client.request.return_value = APIResponse(
        200, [{"name": "prometheus", "enabled": True, "always_on": False}]
    )
    assert mgr_module.list_(client).data[0]["name"] == "prometheus"
    client.request.assert_called_once_with("GET", "/api/mgr/module", api_version="1.0")


@pytest.mark.parametrize(
    "function,suffix",
    [(mgr_module.get_config, ""), (mgr_module.options, "/options")],
)
def test_mapping_reads_use_api_v1(client, function, suffix):
    client.request.return_value = APIResponse(200, {})
    function(client, "prometheus")
    client.request.assert_called_once_with(
        "GET", f"/api/mgr/module/prometheus{suffix}", api_version="1.0"
    )


def test_set_config_preserves_json_scalars_and_null(client):
    config = {"server_port": 9283, "enabled": True, "ratio": 1.5, "note": "x", "reset": None}
    mgr_module.set_config(client, "prometheus", config)
    client.request.assert_called_once_with(
        "PUT",
        "/api/mgr/module/prometheus",
        api_version="1.0",
        data={"config": config},
    )


def test_enable_omits_current_only_force_by_default(client):
    mgr_module.enable(client, "prometheus")
    client.request.assert_called_once_with(
        "POST", "/api/mgr/module/prometheus/enable", api_version="1.0", data={}
    )


def test_enable_can_send_current_release_force(client):
    mgr_module.enable(client, "prometheus", force=True)
    assert client.request.call_args.kwargs["data"] == {"force": True}


def test_disable_uses_empty_body(client):
    mgr_module.disable(client, "prometheus")
    client.request.assert_called_once_with(
        "POST", "/api/mgr/module/prometheus/disable", api_version="1.0", data={}
    )


@pytest.mark.parametrize(
    "call,args",
    [
        (mgr_module.get_config, ("bad/module",)),
        (mgr_module.options, ("selftest",)),
        (mgr_module.set_config, ("prometheus", [])),
        (mgr_module.set_config, ("prometheus", {"bad key": 1})),
        (mgr_module.set_config, ("prometheus", {"nested": {"value": 1}})),
        (mgr_module.set_config, ("prometheus", {"ratio": float("nan")})),
        (mgr_module.enable, ("prometheus", "true")),
    ],
)
def test_operations_reject_invalid_input_before_http(client, call, args):
    with pytest.raises(ConfigurationError):
        call(client, *args)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "call,payload",
    [
        (mgr_module.list_, {}),
        (lambda client: mgr_module.get_config(client, "prometheus"), []),
        (lambda client: mgr_module.options(client, "prometheus"), []),
    ],
)
def test_reads_reject_invalid_response(client, call, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        call(client)
