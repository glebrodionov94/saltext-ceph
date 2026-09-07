"""Unit checks for storage live-test baseline gates."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from saltext.ceph.utils.ceph.errors import APIError
from tests.integration.states import test_live_storage_states as live_storage


def _response(data):
    return SimpleNamespace(data=data)


class _Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


_RGW_SERVICE = "rgw.saltext-ci-rgw"
_RGW_HOST = "ceph-01"
_RGW_DAEMON = "saltext-ci-rgw.ceph-01.test"


def _rgw_daemon_response():
    return _response(
        [
            {
                "id": _RGW_DAEMON,
                "service_map_id": "saltext-ci-rgw.ceph-01.test",
                "server_hostname": _RGW_HOST,
            }
        ]
    )


def _patch_clock(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(live_storage.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(live_storage.time, "sleep", clock.sleep)
    return clock


def test_up_osd_gate_accepts_dashboard_boolean_and_state_shapes(monkeypatch):
    osds = [
        {"id": 1, "up": 1, "in": 1},
        {"id": 2, "state": ["exists", "up"], "in": 1},
        {"id": 3, "up": True, "in": True},
    ]
    monkeypatch.setattr(live_storage.osd_resource, "list_", lambda _client: _response(osds))

    assert live_storage._require_up_osds(object()) == osds


def test_up_osd_gate_rejects_down_or_out_members(monkeypatch):
    osds = [
        {"id": 1, "up": 1, "in": 1},
        {"id": 2, "up": 0, "in": 1},
        {"id": 3, "up": 1, "in": 0},
    ]
    monkeypatch.setattr(live_storage.osd_resource, "list_", lambda _client: _response(osds))

    with pytest.raises(pytest.skip.Exception, match="three|3 up/in"):
        live_storage._require_up_osds(object())


def test_effective_config_prefers_mon_then_global_then_default(monkeypatch):
    config = {
        "value": [
            {"section": "global", "value": "global-value"},
            {"section": "mon", "value": "mon-value"},
        ],
        "default": "default-value",
    }
    monkeypatch.setattr(
        live_storage.cluster_configuration,
        "get",
        lambda _client, _name: _response(config),
    )

    assert (
        live_storage._effective_config(object(), "option", sections=("mon", "global"))
        == "mon-value"
    )
    assert live_storage._effective_config(object(), "option") == "global-value"


@pytest.mark.parametrize("configured", (False, "false", None))
def test_storage_baseline_requires_pool_delete(monkeypatch, configured):
    monkeypatch.setattr(live_storage, "_require_up_osds", lambda _client: None)
    monkeypatch.setattr(
        live_storage,
        "_effective_config",
        lambda *_args, **_kwargs: configured,
    )

    with pytest.raises(pytest.skip.Exception, match="mon_allow_pool_delete"):
        live_storage._require_storage_baseline(object())


def test_storage_baseline_accepts_three_osds_and_pool_delete(monkeypatch):
    require_osds = Mock()
    monkeypatch.setattr(
        live_storage,
        "_require_up_osds",
        require_osds,
    )
    monkeypatch.setattr(
        live_storage,
        "_effective_config",
        lambda *_args, **_kwargs: True,
    )
    client = object()

    live_storage._require_storage_baseline(client)

    require_osds.assert_called_once_with(client)


def test_rgw_daemon_selection_requires_exact_service_and_host():
    daemons = [
        {
            "id": "saltext-ci-rgw-other.ceph-01.test",
            "service_map_id": "saltext-ci-rgw-other.ceph-01.test",
            "server_hostname": _RGW_HOST,
        },
        {
            "id": _RGW_DAEMON,
            "service_map_id": "saltext-ci-rgw.ceph-01.test",
            "server_hostname": _RGW_HOST,
        },
        {
            "id": "saltext-ci-rgw.ceph-02.test",
            "service_map_id": "saltext-ci-rgw.ceph-02.test",
            "server_hostname": "ceph-02",
        },
    ]

    assert live_storage._rgw_daemon_for_service(daemons, _RGW_SERVICE, _RGW_HOST) == _RGW_DAEMON


def test_rgw_ownership_reads_are_scoped_to_selected_daemon(monkeypatch):
    client = object()
    marker = "saltext-ci-owner:saltext-ci-user"
    user_list = Mock(return_value=_response(["saltext-ci-user"]))
    user_get = Mock(return_value=_response({"display_name": marker}))
    bucket_list = Mock(return_value=_response(["saltext-ci-bucket"]))
    bucket_get = Mock(return_value=_response({"owner": "saltext-ci-user"}))
    monkeypatch.setattr(live_storage.rgw_user_resource, "list_users", user_list)
    monkeypatch.setattr(live_storage.rgw_user_resource, "get_user", user_get)
    monkeypatch.setattr(live_storage.rgw_bucket_resource, "list_buckets", bucket_list)
    monkeypatch.setattr(live_storage.rgw_bucket_resource, "get_bucket", bucket_get)

    assert (
        live_storage._owned_rgw_user(
            client,
            "saltext-ci-user",
            marker,
            _RGW_DAEMON,
        )["display_name"]
        == marker
    )
    assert (
        live_storage._owned_rgw_bucket(
            client,
            "saltext-ci-bucket",
            "saltext-ci-user",
            _RGW_DAEMON,
        )["owner"]
        == "saltext-ci-user"
    )
    user_list.assert_called_once_with(client, daemon_name=_RGW_DAEMON)
    user_get.assert_called_once_with(client, "saltext-ci-user", daemon_name=_RGW_DAEMON)
    bucket_list.assert_called_once_with(client, daemon_name=_RGW_DAEMON)
    bucket_get.assert_called_once_with(client, "saltext-ci-bucket", daemon_name=_RGW_DAEMON)


def _rgw_resources():
    return live_storage._RgwLifecycleResources(
        service_name=_RGW_SERVICE,
        service_host=_RGW_HOST,
        uid="saltext-ci-user",
        owner_marker="saltext-ci-owner:saltext-ci-user",
        bucket="saltext-ci-bucket",
        daemon_name=_RGW_DAEMON,
    )


def test_rgw_cleanup_skips_reads_after_all_absences_are_confirmed(monkeypatch):
    owned_bucket = Mock()
    owned_user = Mock()
    owned_service = Mock()
    bucket_absent = Mock()
    user_absent = Mock()
    service_absent = Mock()
    monkeypatch.setattr(live_storage, "_owned_rgw_bucket", owned_bucket)
    monkeypatch.setattr(live_storage, "_owned_rgw_user", owned_user)
    monkeypatch.setattr(live_storage, "_owned_service", owned_service)
    monkeypatch.setattr(live_storage.rgw_bucket_state, "absent", bucket_absent)
    monkeypatch.setattr(live_storage.rgw_user_state, "absent", user_absent)
    monkeypatch.setattr(live_storage.service_state, "absent", service_absent)

    live_storage._cleanup_rgw_resources(
        object(),
        _rgw_resources(),
        claims_proven=True,
        confirmed_absent={"bucket", "user", "service"},
    )

    owned_bucket.assert_not_called()
    owned_user.assert_not_called()
    owned_service.assert_not_called()
    bucket_absent.assert_not_called()
    user_absent.assert_not_called()
    service_absent.assert_not_called()


def test_rgw_cleanup_still_removes_unconfirmed_claimed_resources(monkeypatch):
    client = object()
    owned_bucket = Mock(return_value={"owner": "saltext-ci-user"})
    owned_user = Mock(return_value={"display_name": "saltext-ci-owner:saltext-ci-user"})
    owned_service = Mock(return_value={"service_name": _RGW_SERVICE})
    success = {"result": True, "comment": "removed"}
    bucket_absent = Mock(return_value=success)
    user_absent = Mock(return_value=success)
    service_absent = Mock(return_value=success)
    monkeypatch.setattr(live_storage, "_owned_rgw_bucket", owned_bucket)
    monkeypatch.setattr(live_storage, "_owned_rgw_user", owned_user)
    monkeypatch.setattr(live_storage, "_owned_service", owned_service)
    monkeypatch.setattr(live_storage.rgw_bucket_state, "absent", bucket_absent)
    monkeypatch.setattr(live_storage.rgw_user_state, "absent", user_absent)
    monkeypatch.setattr(live_storage.service_state, "absent", service_absent)

    live_storage._cleanup_rgw_resources(
        client,
        _rgw_resources(),
        claims_proven=True,
        confirmed_absent=set(),
    )

    owned_bucket.assert_called_once_with(
        client,
        "saltext-ci-bucket",
        "saltext-ci-user",
        _RGW_DAEMON,
    )
    bucket_absent.assert_called_once_with(
        "saltext-ci-bucket",
        daemon_name=_RGW_DAEMON,
        confirm=True,
        profile="live",
        task_interval=0.5,
    )
    owned_user.assert_called_once_with(
        client,
        "saltext-ci-user",
        "saltext-ci-owner:saltext-ci-user",
        _RGW_DAEMON,
    )
    user_absent.assert_called_once_with(
        "saltext-ci-user",
        daemon_name=_RGW_DAEMON,
        confirm=True,
        profile="live",
        task_interval=0.5,
    )
    owned_service.assert_called_once_with(client, _RGW_SERVICE, _RGW_HOST)
    service_absent.assert_called_once_with(
        _RGW_SERVICE,
        confirm=True,
        profile="live",
        task_interval=0.5,
    )


def test_rgw_cleanup_before_claim_proof_only_removes_owned_service(monkeypatch):
    client = object()
    owned_bucket = Mock()
    owned_user = Mock()
    owned_service = Mock(return_value={"service_name": _RGW_SERVICE})
    service_absent = Mock(return_value={"result": True, "comment": "removed"})
    monkeypatch.setattr(live_storage, "_owned_rgw_bucket", owned_bucket)
    monkeypatch.setattr(live_storage, "_owned_rgw_user", owned_user)
    monkeypatch.setattr(live_storage, "_owned_service", owned_service)
    monkeypatch.setattr(live_storage.service_state, "absent", service_absent)

    live_storage._cleanup_rgw_resources(
        client,
        _rgw_resources(),
        claims_proven=False,
        confirmed_absent=set(),
    )

    owned_bucket.assert_not_called()
    owned_user.assert_not_called()
    owned_service.assert_called_once_with(client, _RGW_SERVICE, _RGW_HOST)
    service_absent.assert_called_once()


@pytest.mark.parametrize("status", (404, 500, 503))
def test_wait_for_rgw_ready_retries_expected_daemon_errors(monkeypatch, status):
    clock = _patch_clock(monkeypatch)
    daemon_list = Mock(side_effect=(APIError(status), _rgw_daemon_response()))
    user_list = Mock(return_value=_response([]))
    monkeypatch.setattr(live_storage.rgw_daemon_resource, "list_daemons", daemon_list)
    monkeypatch.setattr(live_storage.rgw_user_resource, "list_users", user_list)
    client = object()

    assert (
        live_storage._wait_for_rgw_ready(
            client,
            _RGW_SERVICE,
            _RGW_HOST,
            timeout=5.0,
            interval=1.0,
        )
        == _RGW_DAEMON
    )
    assert clock.sleeps == [1.0]
    user_list.assert_called_once_with(client, daemon_name=_RGW_DAEMON)


@pytest.mark.parametrize("status", (404, 500, 503))
def test_wait_for_rgw_ready_retries_expected_user_errors(monkeypatch, status):
    clock = _patch_clock(monkeypatch)
    daemon_list = Mock(return_value=_rgw_daemon_response())
    user_list = Mock(side_effect=(APIError(status), _response([])))
    monkeypatch.setattr(live_storage.rgw_daemon_resource, "list_daemons", daemon_list)
    monkeypatch.setattr(live_storage.rgw_user_resource, "list_users", user_list)

    assert (
        live_storage._wait_for_rgw_ready(
            object(),
            _RGW_SERVICE,
            _RGW_HOST,
            timeout=5.0,
            interval=1.0,
        )
        == _RGW_DAEMON
    )
    assert clock.sleeps == [1.0]
    assert user_list.call_count == 2


@pytest.mark.parametrize("endpoint", ("daemon", "user"))
def test_wait_for_rgw_ready_propagates_unexpected_api_errors(monkeypatch, endpoint):
    clock = _patch_clock(monkeypatch)
    daemon_result = APIError(401) if endpoint == "daemon" else _rgw_daemon_response()
    user_result = APIError(401) if endpoint == "user" else _response([])
    monkeypatch.setattr(
        live_storage.rgw_daemon_resource,
        "list_daemons",
        (
            Mock(side_effect=daemon_result)
            if endpoint == "daemon"
            else Mock(return_value=daemon_result)
        ),
    )
    monkeypatch.setattr(
        live_storage.rgw_user_resource,
        "list_users",
        Mock(side_effect=user_result) if endpoint == "user" else Mock(return_value=user_result),
    )

    with pytest.raises(APIError) as exc_info:
        live_storage._wait_for_rgw_ready(
            object(),
            _RGW_SERVICE,
            _RGW_HOST,
            timeout=5.0,
            interval=1.0,
        )

    assert exc_info.value.status == 401
    assert not clock.sleeps


def test_wait_for_rgw_ready_times_out_with_last_admin_ops_error(monkeypatch):
    clock = _patch_clock(monkeypatch)
    monkeypatch.setattr(
        live_storage.rgw_daemon_resource,
        "list_daemons",
        Mock(return_value=_rgw_daemon_response()),
    )
    monkeypatch.setattr(
        live_storage.rgw_user_resource,
        "list_users",
        Mock(side_effect=APIError(500)),
    )

    with pytest.raises(pytest.fail.Exception, match=r"/api/rgw/user returned HTTP 500"):
        live_storage._wait_for_rgw_ready(
            object(),
            _RGW_SERVICE,
            _RGW_HOST,
            timeout=5.0,
            interval=3.0,
        )

    assert clock.sleeps == [3.0, 2.0]
