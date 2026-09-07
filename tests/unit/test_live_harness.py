from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.integration import _live
from tests.integration import conftest as live_conftest

FSID = "11111111-2222-4333-8444-555555555555"
RUN_UUID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _token_environment(**updates):
    environment = {
        "CEPH_TEST_URL": "https://ceph.example.test:8443",
        "CEPH_TEST_TOKEN": "header.payload.signature",
    }
    environment.update(updates)
    return environment


def test_read_only_settings_are_opt_in_and_redacted():
    token = "header.payload.top-secret"
    settings = _live.load_settings(
        live=True,
        environ=_token_environment(CEPH_TEST_TOKEN=token),
    )

    assert settings.config is settings.connection
    assert settings.live is True
    assert settings.flags == {"live": True, "mutate": False, "destructive": False}
    assert settings.connection.token == token
    assert settings.mutate is False
    assert token not in repr(settings)
    assert settings.connection.url not in repr(settings)


def test_live_settings_reject_running_without_live_flag():
    with pytest.raises(_live.LiveConfigurationError, match="--ceph-live"):
        _live.load_settings(live=False, environ={})


@pytest.mark.parametrize(
    "flags,message",
    [
        ({"live": False, "mutate": True, "destructive": False}, "--ceph-live"),
        (
            {"live": True, "mutate": False, "destructive": True},
            "--ceph-live-mutate",
        ),
    ],
)
def test_live_flags_are_cumulative(flags, message):
    with pytest.raises(_live.LiveConfigurationError, match=message):
        _live.validate_flag_hierarchy(**flags)


def test_credentials_can_come_from_safe_files(tmp_path):
    username_file = tmp_path / "username"
    password_file = tmp_path / "password"
    username_file.write_text("admin\n", encoding="utf-8")
    password_file.write_text("file-secret\n", encoding="utf-8")

    settings = _live.load_settings(
        live=True,
        environ={
            "CEPH_TEST_URL": "https://ceph.example.test:8443",
            "CEPH_TEST_USERNAME_FILE": str(username_file),
            "CEPH_TEST_PASSWORD_FILE": str(password_file),
        },
    )

    assert settings.connection.username == "admin"
    assert settings.connection.password == "file-secret"
    assert "file-secret" not in repr(settings)


def test_direct_and_file_credential_sources_are_mutually_exclusive(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("file-token", encoding="utf-8")
    environment = _token_environment(CEPH_TEST_TOKEN_FILE=str(token_file))

    with pytest.raises(_live.LiveConfigurationError) as caught:
        _live.load_settings(live=True, environ=environment)

    message = str(caught.value)
    assert "CEPH_TEST_TOKEN" in message
    assert "file-token" not in message
    assert str(token_file) not in message


def test_unsafe_credential_file_error_does_not_reveal_path(tmp_path):
    missing = tmp_path / "missing-secret"

    with pytest.raises(_live.LiveConfigurationError) as caught:
        _live.load_settings(
            live=True,
            environ={
                "CEPH_TEST_URL": "https://ceph.example.test:8443",
                "CEPH_TEST_TOKEN_FILE": str(missing),
            },
        )

    assert str(missing) not in str(caught.value)


def test_mutation_requires_expected_fsid():
    with pytest.raises(_live.LiveConfigurationError, match="EXPECTED_FSID"):
        _live.load_settings(live=True, mutate=True, environ=_token_environment())


def test_owned_metadata_mutation_needs_fsid_but_not_infrastructure_allowlist():
    settings = _live.load_settings(
        live=True,
        mutate=True,
        environ=_token_environment(CEPH_TEST_EXPECTED_FSID=FSID),
    )

    assert settings.require_mutation() == FSID
    assert settings.connection.expected_fsid == FSID
    assert settings.destructive_allowlist == frozenset()


@pytest.mark.parametrize("fsid", ["not-a-uuid", "{11111111-2222-4333-8444-555555555555}"])
def test_expected_fsid_must_be_canonical(fsid):
    with pytest.raises(_live.LiveConfigurationError, match="canonical UUID"):
        _live.load_settings(
            live=True,
            mutate=True,
            environ=_token_environment(CEPH_TEST_EXPECTED_FSID=fsid),
        )


def test_destructive_mode_requires_exact_fsid_confirmation():
    environment = _token_environment(
        CEPH_TEST_EXPECTED_FSID=FSID,
        CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        CEPH_TEST_DESTRUCTIVE_ALLOWLIST="pool:saltext-live",
    )

    with pytest.raises(_live.LiveConfigurationError, match="exactly match"):
        _live.load_settings(
            live=True,
            mutate=True,
            destructive=True,
            environ=environment,
        )


def test_destructive_mode_requires_a_non_wildcard_allowlist():
    environment = _token_environment(
        CEPH_TEST_EXPECTED_FSID=FSID,
        CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID=FSID,
        CEPH_TEST_DESTRUCTIVE_ALLOWLIST="pool:saltext-*",
    )

    with pytest.raises(_live.LiveConfigurationError, match="exact resource"):
        _live.load_settings(
            live=True,
            mutate=True,
            destructive=True,
            environ=environment,
        )


def test_destructive_resource_must_be_exactly_allowlisted():
    settings = _live.load_settings(
        live=True,
        mutate=True,
        destructive=True,
        environ=_token_environment(
            CEPH_TEST_EXPECTED_FSID=FSID,
            CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID=FSID,
            CEPH_TEST_DESTRUCTIVE_ALLOWLIST="pool:saltext-live,host:node-2",
        ),
    )

    assert settings.require_destructive("pool:saltext-live") == FSID
    with pytest.raises(_live.LiveConfigurationError, match="absent"):
        settings.require_destructive("pool:someone-else")
    with pytest.raises(_live.LiveConfigurationError, match="declare"):
        settings.require_destructive()


def test_features_and_transport_settings_are_parsed_without_network_access():
    settings = _live.load_settings(
        live=True,
        environ=_token_environment(
            CEPH_TEST_FEATURES="orchestrator, rgw\ncephfs",
            CEPH_TEST_VERIFY="false",
            CEPH_TEST_CONNECT_TIMEOUT="2.5",
            CEPH_TEST_READ_TIMEOUT="45",
        ),
    )

    assert settings.features == frozenset(("orchestrator", "rgw", "cephfs"))
    assert settings.has_feature("RGW") is True
    assert settings.has_feature("nfs") is False
    assert settings.require_features("RGW", "nfs") == {"nfs"}
    assert settings.connection.verify is False
    assert settings.connection.connect_timeout == 2.5
    assert settings.connection.read_timeout == 45.0


def _guard(level="live"):
    environment = _token_environment()
    options = {"live": True}
    resources = ()
    if level in ("mutate", "destructive"):
        environment["CEPH_TEST_EXPECTED_FSID"] = FSID
        options["mutate"] = True
    if level == "destructive":
        environment["CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID"] = FSID
        environment["CEPH_TEST_DESTRUCTIVE_ALLOWLIST"] = "pool:saltext-live"
        options["destructive"] = True
        resources = ("pool:saltext-live",)
    settings = _live.load_settings(environ=environment, **options)
    transport = Mock(config=settings.connection, closed=False)
    transport.request.return_value = object()
    return (
        _live.GuardedLiveClient(
            transport,
            settings,
            level=level,
            destructive_resources=resources,
        ),
        transport,
    )


def test_guarded_live_client_defaults_to_read_only():
    client, transport = _guard()
    expected = transport.request.return_value

    assert client.request("GET", "/api/health/minimal", api_version="1.0") is expected
    with pytest.raises(_live.LiveConfigurationError, match="Read-only"):
        client.request("POST", "/api/role", api_version="1.0", data={})

    assert transport.request.call_count == 1


def test_metadata_guard_requires_exact_lease_route_and_marker():
    client, transport = _guard("mutate")
    name = f"saltext-ci-role-{RUN_UUID}"
    marker = f"saltext-ci-owner:{RUN_UUID}"

    with pytest.raises(_live.LiveConfigurationError, match="no active ownership"):
        client.request(
            "POST",
            "/api/role",
            api_version="1.0",
            data={"name": name, "description": marker},
        )

    with client.owned_metadata("role", name, marker):
        client.request(
            "POST",
            "/api/role",
            api_version="1.0",
            data={"name": name, "description": marker},
        )
        client.request(
            "PUT",
            f"/api/role/{name}",
            api_version="1.0",
            data={"description": f"{marker}:updated"},
        )
        client.request("DELETE", f"/api/role/{name}", api_version="1.0")
        with pytest.raises(_live.LiveConfigurationError, match="ownership marker"):
            client.request(
                "PUT",
                f"/api/role/{name}",
                api_version="1.0",
                data={"description": "someone-else"},
            )
        with pytest.raises(_live.LiveConfigurationError, match="does not match"):
            client.request(
                "DELETE",
                "/api/role/administrator",
                api_version="1.0",
            )

    assert transport.request.call_count == 3


def test_user_guard_does_not_disclose_rejected_password():
    client, transport = _guard("mutate")
    name = f"saltext-ci-user-{RUN_UUID}"
    marker = f"saltext-ci-owner:{RUN_UUID}"
    password = "private-dashboard-password"

    with client.owned_metadata("user", name, marker):
        with pytest.raises(_live.LiveConfigurationError) as caught:
            client.request(
                "POST",
                "/api/user",
                api_version="1.0",
                data={"username": name, "name": "wrong", "password": password},
            )

    assert password not in str(caught.value)
    transport.request.assert_not_called()


def test_destructive_guard_fails_closed_after_allowlist_validation():
    client, transport = _guard("destructive")

    with pytest.raises(_live.LiveConfigurationError, match="No destructive"):
        client.request(
            "DELETE",
            "/api/pool/saltext-live",
            api_version="1.0",
        )

    transport.request.assert_not_called()


class _FakeConfig:
    def __init__(self, **options):
        self.options = options
        self.option = SimpleNamespace(showlocals=True)

    def getoption(self, name):
        return self.options[name]


class _FakeItem:
    def __init__(self, path, *markers):
        self.fspath = path
        self.markers = list(markers)

    def add_marker(self, marker):
        self.markers.append(marker.mark)

    def get_closest_marker(self, name):
        return next((marker for marker in reversed(self.markers) if marker.name == name), None)

    def iter_markers(self, name):
        return (marker for marker in reversed(self.markers) if marker.name == name)


def test_pytest_live_mode_forces_showlocals_off():
    config = _FakeConfig(ceph_live=True, ceph_live_mutate=False, ceph_live_destructive=False)

    live_conftest.pytest_configure(config)

    assert config.option.showlocals is False


def test_named_live_test_is_skipped_before_setup_without_explicit_flag():
    config = _FakeConfig(ceph_live=False, ceph_live_mutate=False, ceph_live_destructive=False)
    item = _FakeItem("tests/integration/modules/test_live_example.py")

    live_conftest.pytest_collection_modifyitems(config, [item])

    assert item.get_closest_marker("ceph_live") is not None
    skipped = item.get_closest_marker("skip")
    assert skipped is not None
    assert skipped.kwargs["reason"] == "requires explicit --ceph-live"


def test_named_live_module_is_detected_without_importing_its_fixture():
    item = SimpleNamespace(fspath="tests/integration/test_live_dashboard.py")

    assert live_conftest._is_named_live_test(item) is True
    assert (
        live_conftest._is_named_live_test(
            SimpleNamespace(fspath="tests/integration/modules/test_live_host.py")
        )
        is True
    )
    assert (
        live_conftest._is_named_live_test(SimpleNamespace(fspath="tests/unit/test_ceph_client.py"))
        is False
    )
