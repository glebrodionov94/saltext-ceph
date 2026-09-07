"""Pure RGW state normalization tests."""

import os

import pytest

from saltext.ceph.utils.ceph import rgw_state
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError


def test_find_unique_accepts_multiple_identity_key_names():
    assert rgw_state.find_unique([{"RoleName": "one"}], "one", ("RoleName", "name"), "roles") == {
        "RoleName": "one"
    }


def test_find_unique_rejects_duplicates():
    with pytest.raises(ProtocolError, match="duplicate"):
        rgw_state.find_unique([{"name": "one"}, {"name": "one"}], "one", ("name",), "roles")


@pytest.mark.parametrize("value", ("not-json", [], None))
def test_json_value_rejects_invalid_mapping(value):
    with pytest.raises(ConfigurationError):
        rgw_state.json_value(value, "document", mapping_only=True)


def test_json_text_is_canonical():
    assert rgw_state.json_text('{"b":2,"a":1}', "document") == '{"a":1,"b":2}'


def test_canonical_sorts_mapping_keys_and_list_items():
    assert rgw_state.canonical({"b": [2, 1], "a": 1}) == {"a": 1, "b": [1, 2]}


@pytest.mark.parametrize(
    ("value", "expected"),
    ((True, True), (False, False), ("true", True), ("FALSE", False), (1, True), (0, False)),
)
def test_response_bool_normalizes_admin_ops_values(value, expected):
    assert rgw_state.response_bool(value, "enabled") is expected


def test_response_bool_rejects_float_lookalike():
    with pytest.raises(ProtocolError, match="not a boolean"):
        rgw_state.response_bool(1.0, "enabled")


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("Enabled", "Enabled"),
        (" suspended ", "Suspended"),
        ("OFF", "Off"),
        ({"Status": "Off"}, "Off"),
        ({"status": "enabled"}, "Enabled"),
    ),
)
def test_versioning_status_normalizes_supported_dashboard_shapes(value, expected):
    assert rgw_state.versioning_status(value) == expected


@pytest.mark.parametrize("value", (None, "", "Disabled", {}, {"Status": None}, []))
def test_versioning_status_rejects_unknown_or_missing_values(value):
    with pytest.raises(ProtocolError, match="usable versioning status"):
        rgw_state.versioning_status(value)


def test_rate_view_accepts_nested_radosgw_admin_shape():
    value = {
        "user_ratelimit": {
            "enabled": "true",
            "max_read_ops": 1,
            "max_write_ops": 2,
            "max_read_bytes": 3,
            "max_write_bytes": 4,
        }
    }
    assert rgw_state.rate_view(value, "user") == {
        "enabled": True,
        "max_read_ops": 1,
        "max_write_ops": 2,
        "max_read_bytes": 3,
        "max_write_bytes": 4,
    }


@pytest.mark.parametrize(
    "value",
    (
        ["arn:one", "arn:two"],
        {"Policies": [{"PolicyArn": "arn:one"}, {"policy_arn": "arn:two"}]},
    ),
)
def test_policy_arns_normalizes_supported_shapes(value):
    assert rgw_state.policy_arns(value) == ["arn:one", "arn:two"]


def test_validate_secret_sources_rejects_relative_path(tmp_path, monkeypatch):
    secret = tmp_path / "secret"
    secret.write_text("value", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigurationError, match="absolute"):
        rgw_state.validate_secret_sources(os.path.basename(secret))
