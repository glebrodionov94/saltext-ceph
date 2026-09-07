"""Tests for exact-target GitOps orchestration."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from salt.exceptions import SaltRunnerError

from saltext.ceph.runners import ceph_gitops

FSID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(ceph_gitops, "__opts__", {"conf_file": "master"}, raising=False)
    monkeypatch.setattr(ceph_gitops, "__context__", {}, raising=False)


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cmd(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return next(self.responses)


def install_client(monkeypatch, responses):
    client = FakeClient(responses)
    factory = Mock(return_value=client)
    monkeypatch.setattr(ceph_gitops.salt.client, "LocalClient", factory)
    return client, factory


def test_command_uses_one_item_list_target(monkeypatch):
    client, factory = install_client(monkeypatch, [{"ceph-control": True}])
    assert ceph_gitops._command("ceph-control", "test.ping", timeout=5) is True
    factory.assert_called_once_with("master")
    args, kwargs = client.calls[0]
    assert args == (["ceph-control"], "test.ping")
    assert kwargs["tgt_type"] == "list"
    assert kwargs["timeout"] == 5


@pytest.mark.parametrize("response", [{}, {"other": True}, {"node": True, "other": True}, []])
def test_command_requires_exactly_selected_response(monkeypatch, response):
    install_client(monkeypatch, [response])
    with pytest.raises(SaltRunnerError, match="exactly"):
        ceph_gitops._command("node", "test.ping")


def test_running_returns_only_state_jobs(monkeypatch):
    jobs = [
        {
            "jid": "1",
            "pid": 42,
            "fun": "state.apply",
            "arg": ["ceph.cluster", {"pillar": {"token": "secret"}}],
            "kwarg": {"pillar": {"password": "secret"}},
            "user": "root",
        },
        {"jid": "2", "fun": "test.ping"},
        "invalid",
    ]
    install_client(monkeypatch, [{"node": jobs}])
    result = ceph_gitops.running("node")
    assert result == [{"fun": "state.apply", "jid": "1", "pid": 42}]
    assert "secret" not in repr(result)


def test_running_redacts_malformed_state_job_metadata_but_still_blocks(monkeypatch):
    jobs = [
        {
            "jid": "secret-jid",
            "pid": "secret-pid",
            "fun": "state.apply\nsecret",
            "arg": [{"token": "secret"}],
        }
    ]
    install_client(monkeypatch, [{"node": jobs}])
    result = ceph_gitops.running("node")
    assert result == [{"fun": "state.<unknown>"}]
    assert "secret" not in repr(result)


def test_plan_verifies_fsid_then_runs_test_mode(monkeypatch):
    client, _factory = install_client(
        monkeypatch,
        [
            {"node": []},
            {"node": {"status": 200, "data": FSID, "headers": {}}},
            {"node": {"ceph-host|-present": {"result": None}}},
        ],
    )
    result = ceph_gitops.plan("node", FSID.upper(), mods="ceph.cluster", timeout=10)
    assert result["ceph-host|-present"]["result"] is None
    functions = [call[0][1] for call in client.calls]
    assert functions == ["saltutil.running", "ceph_health.fsid", "state.apply"]
    state_kwargs = client.calls[-1][1]["kwarg"]
    assert state_kwargs == {
        "test": True,
        "saltenv": "base",
        "queue": False,
        "mods": ["ceph.cluster"],
    }
    assert ceph_gitops.__context__[ceph_gitops._ACTIVE_KEY] == set()


def test_apply_uses_mutating_state_mode(monkeypatch):
    client, _factory = install_client(
        monkeypatch,
        [
            {"node": []},
            {"node": {"status": 200, "data": FSID}},
            {"node": {"result": True}},
        ],
    )
    assert ceph_gitops.apply("node", FSID) == {"result": True}
    assert client.calls[-1][1]["kwarg"]["test"] is False
    assert "mods" not in client.calls[-1][1]["kwarg"]


def test_run_refuses_existing_state_job_before_fsid_lookup(monkeypatch):
    client, _factory = install_client(
        monkeypatch,
        [{"node": [{"jid": "1", "fun": "state.highstate"}]}],
    )
    with pytest.raises(SaltRunnerError, match="already active"):
        ceph_gitops.plan("node", FSID)
    assert len(client.calls) == 1
    assert ceph_gitops.__context__[ceph_gitops._ACTIVE_KEY] == set()


def test_run_refuses_wrong_cluster_before_state_apply(monkeypatch):
    client, _factory = install_client(
        monkeypatch,
        [{"node": []}, {"node": {"status": 200, "data": str(uuid4())}}],
    )
    with pytest.raises(SaltRunnerError, match="different cluster"):
        ceph_gitops.apply("node", FSID)
    assert len(client.calls) == 2


def test_context_lock_prevents_parallel_run(monkeypatch):
    ceph_gitops.__context__[ceph_gitops._ACTIVE_KEY] = {"node"}
    install_client(monkeypatch, [])
    with pytest.raises(SaltRunnerError, match="already active"):
        ceph_gitops.plan("node", FSID)


@pytest.mark.parametrize(
    "function,args",
    [
        (ceph_gitops.plan, ("", FSID)),
        (ceph_gitops.plan, ("node", "invalid")),
        (ceph_gitops.plan, ("node", FSID, [])),
        (ceph_gitops.plan, ("node", FSID, "bad sls")),
        (ceph_gitops.plan, ("node", FSID, None, "bad env")),
        (ceph_gitops.running, ("node", 0)),
    ],
)
def test_invalid_arguments_fail_before_execution(monkeypatch, function, args):
    _client, factory = install_client(monkeypatch, [])
    with pytest.raises(SaltRunnerError):
        function(*args)
    factory.assert_not_called()


def test_invalid_running_shape_is_rejected(monkeypatch):
    install_client(monkeypatch, [{"node": {}}])
    with pytest.raises(SaltRunnerError, match="invalid running-job"):
        ceph_gitops.running("node")
