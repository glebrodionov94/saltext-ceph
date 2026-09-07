"""Dashboard feature-toggle plugin operations and response validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_feature_toggles as execution
from saltext.ceph.utils.ceph import feature_toggles
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_feature_toggles as wrapper


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


@pytest.mark.parametrize(
    "payload",
    [
        {"rbd": True, "mirroring": False, "nfs": True},
        {
            "rbd": True,
            "mirroring": True,
            "iscsi": True,
            "cephfs": True,
            "rgw": True,
            "nfs": True,
            "dashboard": True,
        },
    ],
)
def test_list_uses_versioned_public_route_and_accepts_release_variants(client, payload):
    client.request.return_value = APIResponse(200, payload, {"content-type": "application/json"})

    result = feature_toggles.list_(client)

    assert result.data == payload
    assert result.data is not payload
    assert result.headers == {"content-type": "application/json"}
    client.request.assert_called_once_with("GET", "/api/feature_toggles", api_version="1.0")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [],
        {"rbd": 1},
        {"rbd": "true"},
        {1: True},
        {"": True},
        {"x" * 256: True},
        {str(index): True for index in range(65)},
    ],
)
def test_list_rejects_unexpected_response_shapes(client, payload):
    client.request.return_value = APIResponse(200, payload)

    with pytest.raises(ProtocolError):
        feature_toggles.list_(client)
