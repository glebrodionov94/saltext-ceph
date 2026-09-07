"""Profile validation and cache isolation."""

from dataclasses import asdict
from dataclasses import replace

import pytest

from saltext.ceph.utils.ceph.config import ConnectionConfig
from saltext.ceph.utils.ceph.config import load_profile
from saltext.ceph.utils.ceph.config import validate_path
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.session import clear_cache
from saltext.ceph.utils.ceph.session import get_client


def settings(**changes):
    """Return a complete token profile."""
    return {"url": "https://ceph.example", "token": "secret", **changes}


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "http://ceph.example"},
        {"url": "https://user:secret@ceph.example"},
        {"url": "https://ceph.example/api"},
        {"url": "https://ceph.example/dashboard%2Fapi"},
        {"url": "https://ceph.example/?token=secret"},
        {"url": "https://ceph.example/#secret"},
        {"url": "https://ceph.example:wrong"},
        {"url": "https://ceph.example/../dashboard"},
        {"url": "https://ceph.example/\n"},
        {"username": "salt", "password": "secret"},
        {"token": None},
        {"token": "\r\nsecret"},
        {"verify": None},
        {"verify": ""},
        {"read_timeout": 0},
        {"connect_timeout": -1},
        {"connect_timeout": float("inf")},
        {"read_timeout": True},
        {"allow_http": "false"},
        {"expected_fsid": "not-a-uuid"},
        {"expected_fsid": 42},
    ],
)
def test_invalid_settings(changes):
    with pytest.raises(ConfigurationError):
        ConnectionConfig(**settings(**changes))


def test_explicit_transport_settings():
    config = ConnectionConfig(
        **settings(url="http://ceph.example", allow_http=True, verify="/ca.pem")
    )
    assert config.allow_http is True
    assert config.verify == "/ca.pem"
    assert "secret" not in repr(config)
    assert "ceph.example" not in repr(config)


def test_expected_fsid_is_normalized():
    config = ConnectionConfig(**settings(expected_fsid="F860CA2E-757D-48CE-B74A-87052CAD563F"))
    assert config.expected_fsid == "f860ca2e-757d-48ce-b74a-87052cad563f"


def test_password_file_profile_reads_secret_without_repr(tmp_path):
    source = tmp_path / "dashboard-password"
    source.write_text("file-secret\n", encoding="utf-8")
    opts = {
        "ceph": {
            "profiles": {
                "default": {
                    "url": "https://ceph.example",
                    "username": "salt",
                    "password_file": str(source),
                }
            }
        }
    }
    config = load_profile(opts, {})
    assert config.password == "file-secret"
    assert "file-secret" not in repr(config)
    assert str(source) not in repr(config)


def test_token_file_profile_reads_secret_without_repr(tmp_path):
    source = tmp_path / "dashboard-token"
    source.write_text("header.payload.signature\n", encoding="utf-8")
    opts = {
        "ceph": {
            "profiles": {"default": {"url": "https://ceph.example", "token_file": str(source)}}
        }
    }
    config = load_profile(opts, {})
    assert config.token == "header.payload.signature"
    assert "header.payload.signature" not in repr(config)


def test_file_backed_profile_produces_a_regular_replaceable_config(tmp_path):
    source = tmp_path / "dashboard-token"
    source.write_text("header.payload.signature", encoding="utf-8")
    opts = {
        "ceph": {
            "profiles": {"default": {"url": "https://ceph.example", "token_file": str(source)}}
        }
    }
    config = load_profile(opts, {})

    assert replace(config, read_timeout=10).read_timeout == 10
    assert ConnectionConfig(**asdict(config)) == config


@pytest.mark.parametrize(
    "values",
    [
        {"username": "salt", "password": "secret", "password_file": "/secret"},
        {"token": "secret", "token_file": "/secret"},
        {"username": "salt", "token_file": "/secret"},
        {"password_file": "/secret"},
    ],
)
def test_credential_file_modes_are_mutually_exclusive(values):
    with pytest.raises(ConfigurationError):
        load_profile(
            {"ceph": {"profiles": {"default": {"url": "https://ceph.example", **values}}}},
            {},
        )


def test_pillar_profile_replaces_opts_profile():
    opts = {"ceph": {"profiles": {"default": settings()}}}
    pillar = {
        "ceph": {"profiles": {"default": settings(url="https://other.example", token="other")}}
    }
    assert load_profile(opts, pillar).token == "other"
    pillar["ceph"]["profiles"]["default"] = {"url": "https://other.example"}
    with pytest.raises(ConfigurationError):
        load_profile(opts, pillar)


@pytest.mark.parametrize("profile", [None, "missing", [], ""])
def test_invalid_profile(profile):
    with pytest.raises(ConfigurationError):
        load_profile({}, {}, profile)


def test_profile_cache_reuses_rotates_and_closes():
    opts = {"ceph": {"profiles": {"default": settings(), "second": settings(token="other")}}}
    context = {}
    first = get_client(opts, {}, context)
    second = get_client(opts, {}, context, "second")
    try:
        assert get_client(opts, {}, context) is first
        assert second is not first
        opts["ceph"]["profiles"]["default"]["token"] = "rotated"
        replacement = get_client(opts, {}, context)
        assert replacement is not first
        assert first.closed
        assert not second.closed
        assert clear_cache(context)
        assert replacement.closed
        assert not clear_cache(context)
        assert clear_cache(context, None)
        assert second.closed
    finally:
        clear_cache(context, None)


def test_profile_cache_rotates_when_secret_file_changes(tmp_path):
    source = tmp_path / "dashboard-token"
    source.write_text("first-token", encoding="utf-8")
    opts = {
        "ceph": {
            "profiles": {"default": {"url": "https://ceph.example", "token_file": str(source)}}
        }
    }
    context = {}
    first = get_client(opts, {}, context)
    try:
        source.write_text("second-token", encoding="utf-8")
        replacement = get_client(opts, {}, context)
        assert replacement is not first
        assert first.closed
        assert replacement.config.token == "second-token"
    finally:
        clear_cache(context, None)


def test_removed_profile_closes_old_connection():
    opts = {"ceph": {"profiles": {"default": settings()}}}
    context = {}
    client = get_client(opts, {}, context)
    opts["ceph"]["profiles"].clear()
    with pytest.raises(ConfigurationError):
        get_client(opts, {}, context)
    assert client.closed


def test_encoded_route_parameter_can_contain_a_filesystem_path():
    validate_path("/api/cephfs/snapshot/schedule/fs/%2Fprojects%2Fbackup")
    validate_path("/api/cephfs/snapshot/schedule/fs/%2Fproject%20one%2F%23daily%3F")


@pytest.mark.parametrize(
    "path",
    [
        "/api//host",
        "/api/%2e%2e/auth",
        "/api/%252e%252e/auth",
        "/api/host%",
        "/api/host%2",
        "/api/host%GG",
    ],
)
def test_ambiguous_api_paths_are_rejected(path):
    with pytest.raises(ConfigurationError):
        validate_path(path)
