"""Shared controller validation helpers."""

import math
from unittest.mock import Mock

import pytest

from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError


@pytest.mark.parametrize("value", [None, "", "bad/name", "bad name", 1, "x" * 256])
def test_identifier_rejects_unsafe_values(value):
    with pytest.raises(ConfigurationError):
        validation.identifier(value)


def test_string_list_preserves_order():
    assert validation.string_list(["node2", "node1"], "hosts") == ["node2", "node1"]


def test_mapping_response_copies_data_and_headers():
    data = {"name": "value"}
    response = validation.mapping_response(
        APIResponse(200, data, {"content-type": "application/json"}), "resource"
    )
    data["name"] = "changed"
    assert response.data == {"name": "value"}


def test_mapping_list_response_rejects_mixed_list():
    with pytest.raises(ProtocolError):
        validation.mapping_list_response(APIResponse(200, [{"name": "ok"}, None]), "resources")


def test_helpers_do_not_depend_on_client():
    assert not isinstance(validation.mapping_response(APIResponse(200, {}), "resource"), Mock)


def test_json_value_detaches_nested_mappings_and_sequences():
    source = {"placement": {"hosts": ("node1", "node2")}, "encrypted": True}
    result = validation.json_value(source, "spec")
    source["placement"]["hosts"] = []
    assert result == {
        "placement": {"hosts": ["node1", "node2"]},
        "encrypted": True,
    }


@pytest.mark.parametrize(
    "value",
    [{1: "bad"}, {"value": object()}, {"value": math.inf}, {"value": math.nan}],
)
def test_json_value_rejects_non_json_values(value):
    with pytest.raises(ConfigurationError):
        validation.json_value(value, "spec")


def test_json_value_bounds_nesting_depth():
    value = []
    for _ in range(18):
        value = [value]
    with pytest.raises(ConfigurationError):
        validation.json_value(value, "spec")


@pytest.mark.parametrize("value,expected", [(0, 0), (12, 12), ("12", 12)])
def test_non_negative_integer_normalizes_decimal_strings(value, expected):
    assert validation.non_negative_integer(value, "id") == expected


@pytest.mark.parametrize("value", [True, -1, "-1", "1.0", None])
def test_non_negative_integer_rejects_invalid_values(value):
    with pytest.raises(ConfigurationError):
        validation.non_negative_integer(value, "id")


def test_integer_list_accepts_one_scalar_when_requested():
    assert validation.integer_list("7", "ids", allow_scalar=True) == [7]


@pytest.mark.parametrize("value", [[], [1, 1], "bad", [False]])
def test_integer_list_rejects_invalid_values(value):
    with pytest.raises(ConfigurationError):
        validation.integer_list(value, "ids")


def test_confirmation_accepts_only_explicit_true():
    assert validation.confirmation(True, "Deleting a resource") is True
    with pytest.raises(ConfigurationError, match="requires confirm=True"):
        validation.confirmation(False, "Deleting a resource")
    for value in (None, 1, "true"):
        with pytest.raises(ConfigurationError, match="must be a boolean"):
            validation.confirmation(value)
