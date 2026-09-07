"""CRUSH rule controller operations and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_crush_rule as execution
from saltext.ceph.utils.ceph import crush_rule
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_crush_rule as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(201, None)
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


def test_list_uses_read_api_v2(client):
    client.request.return_value = APIResponse(
        200, [{"rule_id": 1, "rule_name": "replicated_rule", "steps": []}]
    )
    result = crush_rule.list_(client)
    assert result.data[0]["rule_name"] == "replicated_rule"
    client.request.assert_called_once_with("GET", "/api/crush_rule", api_version="2.0")


@pytest.mark.parametrize("payload", [None, {}, ["rule"], [{"rule_name": "rule"}, None]])
def test_list_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        crush_rule.list_(client)


def test_get_uses_read_api_v2(client):
    client.request.return_value = APIResponse(200, {"rule_name": "ssd-rule"})
    result = crush_rule.get(client, "ssd-rule")
    assert result.data == {"rule_name": "ssd-rule"}
    client.request.assert_called_once_with("GET", "/api/crush_rule/ssd-rule", api_version="2.0")


def test_get_rejects_invalid_response(client):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        crush_rule.get(client, "replicated_rule")


def test_create_replicated_omits_current_only_parameters(client):
    crush_rule.create(
        client,
        "replicated_ssd",
        "host",
        device_class="ssd",
        root="default",
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/crush_rule",
        api_version="1.0",
        data={
            "name": "replicated_ssd",
            "failure_domain": "host",
            "device_class": "ssd",
            "root": "default",
        },
    )


def test_create_erasure_maps_erasure_profile_to_ceph_profile(client):
    crush_rule.create(
        client,
        "ec_ssd",
        "host",
        device_class="ssd",
        erasure_profile="ec42",
        pool_type="ERASURE",
    )
    client.request.assert_called_once_with(
        "POST",
        "/api/crush_rule",
        api_version="1.0",
        data={
            "name": "ec_ssd",
            "failure_domain": "host",
            "device_class": "ssd",
            "profile": "ec42",
            "pool_type": "erasure",
        },
    )


@pytest.mark.parametrize(
    "args,kwargs",
    [
        (("bad/name", "host"), {"root": "default"}),
        (("rule", "bad domain"), {"root": "default"}),
        (("rule", "host"), {"root": None}),
        (("rule", "host"), {"root": "default", "erasure_profile": "ec42"}),
        (("rule", "host"), {"pool_type": "erasure", "root": "default"}),
        (("rule", "host"), {"pool_type": "unknown"}),
        (("rule", "host"), {"device_class": "ssd,class"}),
        (("rule", "host"), {"pool_type": 1}),
    ],
)
def test_create_rejects_invalid_payload_before_http(client, args, kwargs):
    with pytest.raises(ConfigurationError):
        crush_rule.create(client, *args, **kwargs)
    client.request.assert_not_called()


def test_delete_uses_write_api_v1(client):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        crush_rule.delete(client, "replicated_ssd")
    client.request.assert_not_called()
    crush_rule.delete(client, "replicated_ssd", confirm=True)
    client.request.assert_called_once_with(
        "DELETE", "/api/crush_rule/replicated_ssd", api_version="1.0"
    )


@pytest.mark.parametrize("operation", ["get", "delete"])
def test_name_validation_happens_before_http(client, operation):
    with pytest.raises(ConfigurationError):
        getattr(crush_rule, operation)(client, "bad/rule")
    client.request.assert_not_called()
