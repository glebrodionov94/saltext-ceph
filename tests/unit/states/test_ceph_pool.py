"""RADOS pool state reconciliation."""

from unittest.mock import Mock

import pytest
from salt.exceptions import CommandExecutionError

from saltext.ceph.states import ceph_pool as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def resource(**changes):
    value = {
        "pool_name": "volumes",
        "pg_num": 32,
        "type": "replicated",
        "size": 3,
        "application_metadata": ["rbd"],
        "configuration": [{"name": "rbd_qos_bps_limit", "value": 1024}],
        "flags_names": "hashpspool",
        "crush_rule": "replicated_rule",
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def reads(monkeypatch, list_values, get_values=None, **extra):
    salt = {
        "ceph_pool.list": Mock(side_effect=list_values),
        "ceph_pool.get": Mock(side_effect=get_values or []),
        **extra,
    }
    monkeypatch.setattr(state, "__salt__", salt)
    return salt


def test_present_is_idempotent_for_managed_values(monkeypatch):
    value = resource()
    salt = {
        "ceph_pool.list": Mock(return_value=envelope([value])),
        "ceph_pool.get": Mock(return_value=envelope(value)),
        "ceph_pool.update": Mock(),
    }
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present(
        "volumes",
        32,
        "replicated",
        application_metadata=["rbd"],
        rule_name="replicated_rule",
        rbd_configuration={"rbd_qos_bps_limit": 1024},
        options={"size": 3},
    )
    assert result["result"] is True
    salt["ceph_pool.update"].assert_not_called()


def test_present_plans_create_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_pool.list": Mock(return_value=envelope([])), "ceph_pool.create": create},
    )
    result = state.present("volumes", 32, "replicated", options={"size": 3})
    assert result["result"] is None
    create.assert_not_called()


def test_present_creates_waits_and_verifies(monkeypatch):
    value = resource()
    list_ = Mock(side_effect=[envelope([]), envelope([value])])
    create = Mock(
        return_value=envelope({"name": "pool/create", "metadata": {"pool_name": "volumes"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": list_,
            "ceph_pool.get": Mock(return_value=envelope(value)),
            "ceph_pool.create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.present(
        "volumes",
        32,
        "replicated",
        application_metadata=["rbd"],
        rule_name="replicated_rule",
        rbd_configuration={"rbd_qos_bps_limit": 1024},
        options={"size": 3},
    )
    assert result["result"] is True
    create.assert_called_once()
    wait.assert_called_once()


def test_present_polls_until_created_pool_is_visible(monkeypatch):
    value = resource()
    sleep = Mock()
    list_ = Mock(side_effect=[envelope([]), envelope([]), envelope([value])])
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[10.0, 10.25]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": list_,
            "ceph_pool.get": Mock(return_value=envelope(value)),
            "ceph_pool.create": Mock(return_value=envelope(status=201)),
        },
    )

    result = state.present(
        "volumes",
        32,
        "replicated",
        application_metadata=["rbd"],
        rule_name="replicated_rule",
        rbd_configuration={"rbd_qos_bps_limit": 1024},
        options={"size": 3},
        task_timeout=5,
        task_interval=1,
    )

    assert result["result"] is True
    assert result["changes"]["new"]["pool_name"] == "volumes"
    assert list_.call_count == 3
    sleep.assert_called_once_with(1.0)


def test_present_reconciles_mutable_drift_returned_after_create(monkeypatch):
    created = resource(pg_num=32)
    after = resource(pg_num=8)
    create = Mock(
        return_value=envelope(
            {"name": "pool/create", "metadata": {"pool_name": "volumes"}},
            status=202,
        )
    )
    update = Mock(
        return_value=envelope(
            {"name": "pool/edit", "metadata": {"pool_name": "volumes"}},
            status=202,
        )
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": Mock(
                side_effect=[envelope([]), envelope([created]), envelope([after])]
            ),
            "ceph_pool.get": Mock(side_effect=[envelope(created), envelope(after)]),
            "ceph_pool.create": create,
            "ceph_pool.update": update,
            "ceph_task.wait": wait,
        },
    )

    result = state.present(
        "volumes",
        8,
        "replicated",
        application_metadata=["rbd"],
        rule_name="replicated_rule",
        rbd_configuration={"rbd_qos_bps_limit": 1024},
        options={"size": 3},
        task_timeout=55,
        task_interval=3,
    )

    assert result["result"] is True
    assert result["changes"]["old"] is None
    assert result["changes"]["new"]["pg_num"] == 8
    update.assert_called_once()
    assert update.call_args.kwargs["options"] == {"pg_num": 8}
    assert wait.call_count == 2
    assert all(call.kwargs["timeout"] == 55 for call in wait.call_args_list)
    assert all(call.kwargs["interval"] == 3 for call in wait.call_args_list)


def test_present_reports_post_create_pg_transition_error(monkeypatch):
    created = resource(pg_num=32)
    update = Mock(
        side_effect=CommandExecutionError(
            "Ceph API HTTP 400: invalid request.", info={"status": 400}
        )
    )
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": Mock(side_effect=[envelope([]), envelope([created])]),
            "ceph_pool.get": Mock(return_value=envelope(created)),
            "ceph_pool.create": Mock(return_value=envelope(status=201)),
            "ceph_pool.update": update,
        },
    )

    result = state.present(
        "volumes",
        8,
        "replicated",
        application_metadata=["rbd"],
        rule_name="replicated_rule",
        rbd_configuration={"rbd_qos_bps_limit": 1024},
        options={"size": 3},
    )

    assert result["result"] is False
    assert "HTTP 400" in result["comment"]
    update.assert_called_once()


def test_present_only_attempts_one_post_create_correction(monkeypatch):
    created = resource(pg_num=32)
    sleep = Mock()
    update = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state.reconcile.time,
        "monotonic",
        Mock(side_effect=[10.0, 20.0, 20.5]),
    )
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": Mock(
                side_effect=[envelope([]), envelope([created]), envelope([created])]
            ),
            "ceph_pool.get": Mock(return_value=envelope(created)),
            "ceph_pool.create": Mock(return_value=envelope(status=201)),
            "ceph_pool.update": update,
        },
    )

    result = state.present(
        "volumes",
        8,
        "replicated",
        application_metadata=["rbd"],
        rule_name="replicated_rule",
        rbd_configuration={"rbd_qos_bps_limit": 1024},
        options={"size": 3},
        task_timeout=0.5,
        task_interval=0.1,
    )

    assert result["result"] is False
    assert "did not converge after mutation" in result["comment"]
    update.assert_called_once()
    sleep.assert_not_called()


def test_present_fails_after_convergence_timeout(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[10.0, 10.5]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": Mock(return_value=envelope([])),
            "ceph_pool.create": Mock(return_value=envelope(status=201)),
        },
    )

    result = state.present(
        "volumes",
        32,
        "replicated",
        task_timeout=0.5,
        task_interval=0.1,
    )

    assert result["result"] is False
    assert not result["changes"]
    assert "did not converge after mutation" in result["comment"]
    sleep.assert_not_called()


def test_present_updates_mutable_fields(monkeypatch):
    before = resource(pg_num=16, size=2, application_metadata=[])
    after = resource()
    list_ = Mock(side_effect=[envelope([before]), envelope([after])])
    get = Mock(side_effect=[envelope(before), envelope(after)])
    update = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_pool.list": list_, "ceph_pool.get": get, "ceph_pool.update": update},
    )
    result = state.present(
        "volumes",
        32,
        "replicated",
        application_metadata=["rbd"],
        options={"size": 3},
    )
    assert result["result"] is True
    assert update.call_args.kwargs["options"] == {"size": 3, "pg_num": 32}
    assert update.call_args.kwargs["application_metadata"] == ["rbd"]


def test_present_rejects_immutable_change(monkeypatch):
    value = resource(type="erasure", erasure_code_profile="ec42")
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": Mock(return_value=envelope([value])),
            "ceph_pool.get": Mock(return_value=envelope(value)),
        },
    )
    result = state.present("volumes", 32, "replicated")
    assert result["result"] is False
    assert "immutable" in result["comment"]


def test_existing_pool_delegates_mirroring_state(monkeypatch):
    value = resource()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": Mock(return_value=envelope([value])),
            "ceph_pool.get": Mock(return_value=envelope(value)),
        },
    )
    result = state.present("volumes", 32, "replicated", rbd_mirroring=True)
    assert result["result"] is False
    assert "ceph_rbd_mirroring" in result["comment"]


def test_absent_requires_confirmation(monkeypatch):
    value = resource()
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": Mock(return_value=envelope([value])),
            "ceph_pool.get": Mock(return_value=envelope(value)),
            "ceph_pool.delete": delete,
        },
    )
    assert state.absent("volumes")["result"] is False
    delete.assert_not_called()


def test_absent_deletes_and_verifies(monkeypatch):
    value = resource()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": Mock(side_effect=[envelope([value]), envelope([])]),
            "ceph_pool.get": Mock(return_value=envelope(value)),
            "ceph_pool.delete": Mock(return_value=envelope(status=204)),
        },
    )
    result = state.absent("volumes", confirm=True)
    assert result["result"] is True


def test_absent_polls_until_deleted_pool_disappears(monkeypatch):
    value = resource()
    sleep = Mock()
    list_ = Mock(side_effect=[envelope([value]), envelope([value]), envelope([])])
    get = Mock(return_value=envelope(value))
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[10.0, 10.25]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_pool.list": list_,
            "ceph_pool.get": get,
            "ceph_pool.delete": Mock(return_value=envelope(status=204)),
        },
    )

    result = state.absent(
        "volumes",
        confirm=True,
        task_timeout=5,
        task_interval=1,
    )

    assert result["result"] is True
    assert result["changes"] == {"old": value, "new": None}
    assert list_.call_count == 3
    assert get.call_count == 2
    sleep.assert_called_once_with(1.0)


def test_absent_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_pool.list": Mock(return_value=envelope([])), "ceph_pool.delete": delete},
    )
    assert state.absent("volumes")["result"] is True
    delete.assert_not_called()


def test_invalid_pool_fails_before_read(monkeypatch):
    list_ = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_pool.list": list_})
    assert state.present("bad pool", 32, "replicated")["result"] is False
    list_.assert_not_called()
