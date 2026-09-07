"""Verify discovery and execution through actual Salt utility and SSH loaders."""

from unittest.mock import Mock

import pytest
import salt.loader
from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph import PACKAGE_ROOT
from saltext.ceph.utils import ceph as ceph_utils
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.client import CephClient
from saltext.ceph.utils.ceph.errors import APIError


def test_utils_loader(minion_opts):
    # Salt 3006 deliberately skips extension entry points for utils. Normal
    # consumers import saltext.ceph.utils.ceph; utils_dirs is an optional route.
    minion_opts["utils_dirs"] = [str(PACKAGE_ROOT / "utils")]
    loader = salt.loader.utils(minion_opts)
    context = {}
    opts = {"ceph": {"profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}}}
    client = loader["ceph.get_client"](opts, {}, context)
    assert client.config.url == "https://ceph.example"
    assert loader["ceph.clear_cache"](context)
    assert client.closed


@pytest.fixture
def wrapper(master_opts):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    yield loader
    loader["ceph.clear_cache"](profile=None)


def test_ceph_grafana_execution_module_routes_validation(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    calls = []

    def request(_client, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return APIResponse(200, 204)

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    result = loader["ceph_grafana.validate_dashboard"]("ceph-cluster")
    assert result["data"] == 204
    assert calls == [
        (
            "GET",
            "/api/grafana/validation/ceph-cluster",
            {"api_version": "1.0"},
        )
    ]
    ceph_utils.clear_cache(context, profile=None)


def test_ceph_grafana_ssh_wrapper_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    calls = []

    def request(client, method, path, **kwargs):
        calls.append((client.config.url, method, path, kwargs))
        return APIResponse(200, {"instance": "https://grafana.example"})

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_grafana.url"]()["data"]["instance"] == "https://grafana.example"
    assert calls == [
        (
            "https://ceph.example",
            "GET",
            "/api/grafana/url",
            {"api_version": "1.0"},
        )
    ]
    loader["ceph.clear_cache"](profile=None)


def test_wrapper_uses_controller_profile(wrapper, monkeypatch):
    captured = []

    def request(client, method, path, **kwargs):
        captured.append((client.config.url, method, path, kwargs))
        return APIResponse(200, {"health": "HEALTH_OK"})

    monkeypatch.setattr(CephClient, "request", request)
    assert wrapper["ceph.query"]("/api/health/minimal", "1.0") == {
        "status": 200,
        "data": {"health": "HEALTH_OK"},
        "headers": {},
    }
    assert captured[0][0] == "https://ceph.example"


def test_wrapper_maps_status_to_salt_error(wrapper, monkeypatch):
    monkeypatch.setattr(CephClient, "request", Mock(side_effect=APIError(403)))
    with pytest.raises(CommandExecutionError, match="403"):
        wrapper["ceph.query"]("/api/host", "1.3")


def test_wrapper_requires_string_version(wrapper):
    with pytest.raises(SaltInvocationError, match="Quote"):
        wrapper["ceph.query"]("/api/host", 1.3)


@pytest.mark.parametrize("method", [None, True, "OPTIONS", "TRACE"])
def test_wrapper_rejects_unsupported_method_before_request(wrapper, monkeypatch, method):
    request = Mock()
    monkeypatch.setattr(CephClient, "request", request)

    with pytest.raises(SaltInvocationError, match="Unsupported HTTP method"):
        wrapper["ceph.query"]("/api/host", "1.3", method=method, confirm=True)
    request.assert_not_called()


def test_wrapper_test_mode_refuses_mutation(master_opts, monkeypatch):
    master_opts["test"] = True
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    request = Mock()
    monkeypatch.setattr(CephClient, "request", request)
    with pytest.raises(SaltInvocationError, match="test=True"):
        loader["ceph.query"]("/api/service", "1.0", method="POST")
    request.assert_not_called()


def test_wrapper_mutation_requires_confirmation(wrapper, monkeypatch):
    request = Mock(return_value=APIResponse(201, None))
    monkeypatch.setattr(CephClient, "request", request)

    with pytest.raises(SaltInvocationError, match="confirm=True"):
        wrapper["ceph.query"]("/api/service", "1.0", method="POST")
    with pytest.raises(SaltInvocationError, match="boolean"):
        wrapper["ceph.query"]("/api/service", "1.0", method="POST", confirm="true")

    assert (
        wrapper["ceph.query"](
            "/api/service", "1.0", method="post", data={"service_name": "mgr"}, confirm=True
        )["status"]
        == 201
    )
    request.assert_called_once_with(
        "POST",
        "/api/service",
        api_version="1.0",
        params=None,
        data={"service_name": "mgr"},
    )


@pytest.fixture
def auth_response():
    return APIResponse(201, {"username": "salt", "permissions": {"hosts": ["read"]}})


def test_auth_execution_module(minion_opts, monkeypatch, auth_response):
    minion_opts["ceph"] = {
        "profiles": {
            "default": {"url": "https://ceph.example", "username": "salt", "password": "secret"}
        }
    }
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    login = Mock(return_value=auth_response)
    check = Mock(return_value=auth_response)
    logout = Mock(return_value=APIResponse(200, {"redirect_url": "#/login"}))
    monkeypatch.setattr(CephClient, "login", login)
    monkeypatch.setattr(CephClient, "check", check)
    monkeypatch.setattr(CephClient, "logout", logout)

    result = loader["ceph_auth.login"](ttl=2)
    assert result["data"]["username"] == "salt"
    login.assert_called_once_with(ttl=2)
    assert loader["ceph_auth.check"]()["status"] == 201
    check.assert_called_once_with()
    assert loader["ceph_auth.logout"]()["status"] == 200
    logout.assert_called_once_with()


def test_auth_ssh_wrapper_ignores_target_pillar(master_opts, monkeypatch, auth_response):
    master_opts["ceph"] = {
        "profiles": {
            "default": {"url": "https://ceph.example", "username": "salt", "password": "secret"}
        }
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example", "token": "other"}}}
    }
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    urls = []

    def login(client, ttl=None):
        urls.append(client.config.url)
        assert ttl is None
        return auth_response

    monkeypatch.setattr(CephClient, "login", login)

    assert loader["ceph_auth.login"]()["data"]["username"] == "salt"
    assert urls == ["https://ceph.example"]
    loader["ceph.clear_cache"](profile=None)


def test_ceph_users_execution_module(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    requests = []

    def request(_client, method, path, **kwargs):
        requests.append((method, path, kwargs))
        if method == "GET":
            return APIResponse(
                200,
                [{"entity": "client.backup", "key": "private", "caps": {"mon": "allow r"}}],
            )
        return APIResponse(201, "created")

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    listed = loader["ceph_users.list"]()
    assert listed["data"][0]["key"] == "***********"
    created = loader["ceph_users.create"]("client.backup", [{"entity": "mon", "cap": "allow r"}])
    assert created["status"] == 201
    assert requests[1] == (
        "POST",
        "/api/cluster/user",
        {
            "api_version": "1.0",
            "data": {
                "user_entity": "client.backup",
                "capabilities": [{"entity": "mon", "cap": "allow r"}],
            },
        },
    )
    ceph_utils.clear_cache(context, profile=None)


def test_ceph_users_ssh_wrapper_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    urls = []

    def request(client, method, path, **kwargs):
        urls.append(client.config.url)
        assert method == "GET"
        assert path == "/api/cluster/user"
        assert kwargs == {"api_version": "1.0"}
        return APIResponse(200, [])

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_users.list"]() == {"status": 200, "data": [], "headers": {}}
    assert urls == ["https://ceph.example"]
    loader["ceph.clear_cache"](profile=None)


def test_ceph_users_loader_maps_validation_errors(minion_opts):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    loader = salt.loader.minion_mods(minion_opts, context={})
    with pytest.raises(SaltInvocationError, match="fully qualified"):
        loader["ceph_users.get"]("invalid")


def test_cephfs_execution_module_routes_and_validates(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    requests = []

    def request(_client, method, path, **kwargs):
        requests.append((method, path, kwargs))
        return APIResponse(200, [])

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    assert loader["cephfs.list"]()["data"] == []
    loader["cephfs.schedule_update"]("archive", "/projects", "7-d")
    assert requests == [
        ("GET", "/api/cephfs", {"api_version": "1.0"}),
        (
            "PUT",
            "/api/cephfs/snapshot/schedule/archive/%2Fprojects",
            {"api_version": "1.0", "data": {"retention_to_add": "7-d"}},
        ),
    ]
    with pytest.raises(SaltInvocationError, match="absolute CephFS path"):
        loader["cephfs.statfs"](1, "relative")
    ceph_utils.clear_cache(context, profile=None)


def test_cephfs_ssh_wrapper_tracks_execution_signatures(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    calls = []

    def request(client, method, path, **kwargs):
        calls.append((client.config.url, method, path, kwargs))
        return APIResponse(200, [])

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["cephfs.group_list"]("archive", info=False)["data"] == []
    assert calls == [
        (
            "https://ceph.example",
            "GET",
            "/api/cephfs/subvolume/group/archive",
            {"api_version": "1.0", "params": {"info": False}},
        )
    ]
    assert "cephfs.mirror_checkpoint_now" in loader
    loader["ceph.clear_cache"](profile=None)


def test_ceph_certificates_execution_module(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    calls = []

    def request(_client, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return APIResponse(200, [])

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    result = loader["ceph_certificates.list"](status="valid", scope="HOST")
    assert result["data"] == []
    assert calls == [
        (
            "GET",
            "/api/service/certificate",
            {"api_version": "1.0", "params": {"status": "valid", "scope": "host"}},
        )
    ]
    ceph_utils.clear_cache(context, profile=None)


def test_ceph_certificates_ssh_wrapper_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    urls = []

    def request(client, method, path, **kwargs):
        urls.append(client.config.url)
        assert method == "GET"
        assert path == "/api/service/certificate/rgw.site"
        assert kwargs == {"api_version": "1.0"}
        return APIResponse(200, {"status": "valid"})

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_certificates.get"]("rgw.site")["data"]["status"] == "valid"
    assert urls == ["https://ceph.example"]
    loader["ceph.clear_cache"](profile=None)


def test_ceph_cluster_execution_module_routes_upgrade(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    calls = []

    def request(_client, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return APIResponse(201, "Initiating upgrade")

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    result = loader["ceph_cluster.upgrade_start"](version="18.2.7", daemon_types=["mgr"], limit=1)
    assert result["status"] == 201
    assert calls == [
        (
            "POST",
            "/api/cluster/upgrade/start",
            {
                "api_version": "1.0",
                "data": {"version": "18.2.7", "daemon_types": ["mgr"], "limit": 1},
            },
        )
    ]
    ceph_utils.clear_cache(context, profile=None)


def test_ceph_cluster_ssh_wrapper_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    calls = []

    def request(client, method, path, **kwargs):
        calls.append((client.config.url, method, path, kwargs))
        return APIResponse(200, {"status": "POST_INSTALLED"})

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_cluster.status"]()["data"]["status"] == "POST_INSTALLED"
    assert calls == [("https://ceph.example", "GET", "/api/cluster", {"api_version": "0.1"})]
    loader["ceph.clear_cache"](profile=None)


def test_ceph_cluster_config_execution_module_routes_set(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    calls = []

    def request(_client, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return APIResponse(201, None)

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    result = loader["ceph_cluster_config.set"]("debug_ms", [{"section": "mon", "value": "0/3"}])
    assert result["status"] == 201
    assert calls == [
        (
            "POST",
            "/api/cluster_conf",
            {
                "api_version": "1.0",
                "data": {
                    "name": "debug_ms",
                    "value": [{"section": "mon", "value": "0/3"}],
                },
            },
        )
    ]
    ceph_utils.clear_cache(context, profile=None)


def test_ceph_cluster_config_ssh_wrapper_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    calls = []

    def request(client, method, path, **kwargs):
        calls.append((client.config.url, method, path, kwargs))
        return APIResponse(200, {"name": "debug_ms"})

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_cluster_config.get"]("debug_ms")["data"]["name"] == "debug_ms"
    assert calls == [
        ("https://ceph.example", "GET", "/api/cluster_conf/debug_ms", {"api_version": "1.0"})
    ]
    loader["ceph.clear_cache"](profile=None)


def test_ceph_crush_rule_execution_module_routes_create(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    calls = []

    def request(_client, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return APIResponse(201, None)

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    result = loader["ceph_crush_rule.create"](
        "replicated_ssd", "host", device_class="ssd", root="default"
    )
    assert result["status"] == 201
    assert calls == [
        (
            "POST",
            "/api/crush_rule",
            {
                "api_version": "1.0",
                "data": {
                    "name": "replicated_ssd",
                    "failure_domain": "host",
                    "device_class": "ssd",
                    "root": "default",
                },
            },
        )
    ]
    ceph_utils.clear_cache(context, profile=None)


def test_ceph_crush_rule_ssh_wrapper_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    calls = []

    def request(client, method, path, **kwargs):
        calls.append((client.config.url, method, path, kwargs))
        return APIResponse(200, {"rule_name": "replicated_rule"})

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_crush_rule.get"]("replicated_rule")["data"]["rule_name"] == (
        "replicated_rule"
    )
    assert calls == [
        (
            "https://ceph.example",
            "GET",
            "/api/crush_rule/replicated_rule",
            {"api_version": "2.0"},
        )
    ]
    loader["ceph.clear_cache"](profile=None)


def test_ceph_daemon_execution_module_routes_action(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    calls = []

    def request(_client, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return APIResponse(200, "Scheduled")

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    result = loader["ceph_daemon.action"]("osd.1", "restart", force=True)
    assert result["data"] == "Scheduled"
    assert calls == [
        (
            "PUT",
            "/api/daemon/osd.1",
            {"api_version": "0.1", "data": {"action": "restart", "force": True}},
        )
    ]
    ceph_utils.clear_cache(context, profile=None)


def test_ceph_daemon_ssh_wrapper_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    calls = []

    def request(client, method, path, **kwargs):
        calls.append((client.config.url, method, path, kwargs))
        return APIResponse(200, [{"daemon_name": "mgr.node1"}])

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_daemon.list"](["mgr"])["data"][0]["daemon_name"] == "mgr.node1"
    assert calls == [
        (
            "https://ceph.example",
            "GET",
            "/api/daemon",
            {"api_version": "1.0", "params": {"daemon_types": ["mgr"]}},
        )
    ]
    loader["ceph.clear_cache"](profile=None)


def test_ceph_erasure_code_profile_execution_routes_create(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    calls = []

    def request(_client, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return APIResponse(201, None)

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    result = loader["ceph_erasure_code_profile.create"](
        "ec42", {"plugin": "jerasure", "k": 4, "m": 2}
    )
    assert result["status"] == 201
    assert calls == [
        (
            "POST",
            "/api/erasure_code_profile",
            {
                "api_version": "1.0",
                "data": {"name": "ec42", "plugin": "jerasure", "k": 4, "m": 2},
            },
        )
    ]
    ceph_utils.clear_cache(context, profile=None)


def test_ceph_erasure_code_profile_ssh_wrapper_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    calls = []

    def request(client, method, path, **kwargs):
        calls.append((client.config.url, method, path, kwargs))
        return APIResponse(200, {"name": "ec42", "k": 4, "m": 2})

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_erasure_code_profile.get"]("ec42")["data"]["name"] == "ec42"
    assert calls == [
        (
            "https://ceph.example",
            "GET",
            "/api/erasure_code_profile/ec42",
            {"api_version": "1.0"},
        )
    ]
    loader["ceph.clear_cache"](profile=None)


def test_plugin_controller_execution_modules_load_with_salt(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    calls = []

    def request(_client, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/api/feature_toggles":
            return APIResponse(200, {"rbd": True, "rgw": False})
        return APIResponse(201, {})

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)

    assert loader["ceph_feature_toggles.list"]()["data"] == {
        "rbd": True,
        "rgw": False,
    }
    assert loader["ceph_motd.create"]("warning", "2h", "Maintenance")["status"] == 201
    assert calls == [
        ("GET", "/api/feature_toggles", {"api_version": "1.0"}),
        (
            "POST",
            "/api/motd",
            {
                "api_version": "1.0",
                "data": {
                    "severity": "warning",
                    "expires": "2h",
                    "message": "Maintenance",
                },
            },
        ),
    ]
    ceph_utils.clear_cache(context, profile=None)
