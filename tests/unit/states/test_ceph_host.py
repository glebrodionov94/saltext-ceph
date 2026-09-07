"""Ceph host state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_host as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def host(address="10.0.0.1", labels=None, status=""):
    return {
        "hostname": "node1",
        "addr": address,
        "labels": labels or [],
        "status": status,
    }


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_present_is_idempotent_with_orderless_labels(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": Mock(return_value=envelope([host(labels=["b", "a"])])),
            "ceph_host.create": create,
        },
    )
    result = state.present("node1", address="10.0.0.1", labels=["a", "b"], maintenance=False)
    assert result["result"] is True
    create.assert_not_called()


def test_present_normalizes_omitted_hostspec_defaults(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": Mock(return_value=envelope([{"hostname": "node1"}])),
            "ceph_host.create": create,
        },
    )

    result = state.present("node1", address="node1", labels=[], maintenance=False)

    assert result["result"] is True
    assert not result["changes"]
    create.assert_not_called()


def test_virtual_requires_host_drain_execution_function(monkeypatch):
    required = {
        "ceph_host.list": Mock(),
        "ceph_host.create": Mock(),
        "ceph_host.delete": Mock(),
        "ceph_host.set_labels": Mock(),
        "ceph_host.toggle_maintenance": Mock(),
    }
    monkeypatch.setattr(state, "__salt__", required)

    result = state.__virtual__()

    assert result[0] is False
    assert "ceph_host.drain" in result[1]


def test_present_plans_creation_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([])), "ceph_host.create": create},
    )
    result = state.present("node1", labels=["storage"])
    assert result["result"] is None
    create.assert_not_called()


def test_present_creates_waits_and_verifies(monkeypatch):
    list_ = Mock(
        side_effect=[
            envelope([]),
            envelope([]),
            envelope([host(labels=["storage"])]),
            envelope([host(labels=["storage"])]),
        ]
    )
    create = Mock(
        return_value=envelope({"name": "host/add", "metadata": {"hostname": "node1"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0, 0.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": list_, "ceph_host.create": create, "ceph_task.wait": wait},
    )
    result = state.present("node1", labels=["storage"])
    assert result["result"] is True
    create.assert_called_once_with(
        "node1",
        address=None,
        labels=["storage"],
        maintenance=False,
        profile="default",
    )
    wait.assert_called_once()
    sleep.assert_called_once_with(2.0)


def test_present_polls_stale_cache_after_update(monkeypatch):
    stale = host(labels=[])
    converged = host(labels=["storage"])
    list_ = Mock(
        side_effect=[
            envelope([stale]),
            envelope([stale]),
            envelope([stale]),
            envelope([converged]),
        ]
    )
    set_labels = Mock(return_value=envelope(status=204))
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": list_, "ceph_host.set_labels": set_labels},
    )

    result = state.present(
        "node1",
        labels=["storage"],
        task_timeout=5,
        task_interval=1,
    )

    assert result["result"] is True
    assert result["changes"]["new"]["labels"] == ["storage"]
    set_labels.assert_called_once_with("node1", ["storage"], profile="default")
    sleep.assert_called_once_with(1.0)


def test_present_reports_bounded_timeout_when_update_stays_stale(monkeypatch):
    stale = host(labels=[])
    update = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 1.0]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": Mock(return_value=envelope([stale])),
            "ceph_host.set_labels": update,
        },
    )

    result = state.present(
        "node1",
        labels=["storage"],
        task_timeout=0.5,
        task_interval=0.1,
    )

    assert result["result"] is False
    assert "did not converge after mutation" in result["comment"]
    update.assert_called_once()


def test_present_reports_bounded_timeout_when_created_host_stays_hidden(monkeypatch):
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 1.0]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([])), "ceph_host.create": create},
    )

    result = state.present(
        "node1",
        task_timeout=0.5,
        task_interval=0.1,
    )

    assert result["result"] is False
    assert "not visible with its declared fields" in result["comment"]
    create.assert_called_once()


def test_present_updates_labels_then_maintenance(monkeypatch):
    list_ = Mock(
        side_effect=[
            envelope([host(labels=[])]),
            envelope([host(labels=["storage"])]),
            envelope([host(labels=["storage"], status="maintenance")]),
        ]
    )
    set_labels = Mock(return_value=envelope(status=204))
    toggle = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": list_,
            "ceph_host.set_labels": set_labels,
            "ceph_host.toggle_maintenance": toggle,
        },
    )
    result = state.present("node1", labels=["storage"], maintenance=True)
    assert result["result"] is True
    set_labels.assert_called_once()
    toggle.assert_called_once_with("node1", force=False, profile="default")


def test_existing_address_mismatch_is_known_failure_even_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([host()]))},
    )
    result = state.present("node1", address="10.0.0.2")
    assert result["result"] is False
    assert "cannot update" in result["comment"]


def test_absent_plans_without_confirmation_in_test_mode(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([host()])), "ceph_host.delete": delete},
    )
    assert state.absent("node1")["result"] is None
    delete.assert_not_called()


def test_absent_requires_confirmation_for_live_delete(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([host()])), "ceph_host.delete": delete},
    )
    result = state.absent("node1")
    assert result["result"] is False
    delete.assert_not_called()


def test_absent_deletes_waits_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([host()]), envelope([host()]), envelope([])])
    delete = Mock(
        return_value=envelope({"name": "host/remove", "metadata": {"hostname": "node1"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": list_, "ceph_host.delete": delete, "ceph_task.wait": wait},
    )
    result = state.absent("node1", confirm=True)
    assert result["result"] is True
    delete.assert_called_once()
    wait.assert_called_once()
    sleep.assert_called_once_with(5.0)


def test_absent_reports_bounded_timeout_when_deleted_host_stays_visible(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 1.0]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([host()])), "ceph_host.delete": delete},
    )

    result = state.absent(
        "node1",
        confirm=True,
        task_timeout=0.5,
        task_interval=0.1,
    )

    assert result["result"] is False
    assert "still exists after deletion" in result["comment"]
    delete.assert_called_once()


def test_absent_can_drain_service_instances_before_stale_delete(monkeypatch):
    running = host()
    running["service_instances"] = [
        {"type": "mgr", "count": 1},
        {"type": "node-exporter", "count": 1},
    ]
    drained = host()
    drained["service_instances"] = []
    list_ = Mock(
        side_effect=[
            envelope([host()]),
            envelope([running]),
            envelope([drained]),
            envelope([host()]),
            envelope([]),
        ]
    )
    drain = Mock(
        return_value=envelope({"name": "host/drain", "metadata": {"hostname": "node1"}}, 202)
    )
    delete = Mock(return_value=envelope(status=204))
    wait = Mock(return_value=envelope({"success": True}))
    sleep = Mock()
    monkeypatch.setattr(
        state.reconcile.time,
        "monotonic",
        Mock(side_effect=[0.0, 0.0, 0.0, 0.0]),
    )
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": list_,
            "ceph_host.drain": drain,
            "ceph_host.delete": delete,
            "ceph_task.wait": wait,
        },
    )

    result = state.absent(
        "node1",
        confirm=True,
        drain=True,
        task_timeout=10,
        task_interval=1,
    )

    assert result["result"] is True
    drain.assert_called_once_with("node1", profile="default")
    delete.assert_called_once_with("node1", confirm=True, profile="default")
    wait.assert_called_once()
    assert [
        invocation.kwargs["include_service_instances"] for invocation in list_.call_args_list
    ] == [
        False,
        True,
        True,
        False,
        False,
    ]
    assert sleep.call_count == 2


def test_absent_drain_times_out_before_delete_when_daemons_remain(monkeypatch):
    running = host()
    running["service_instances"] = [{"type": "mgr", "count": 1}]
    delete = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 1.0]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": Mock(side_effect=[envelope([host()]), envelope([running])]),
            "ceph_host.drain": Mock(return_value=envelope(status=204)),
            "ceph_host.delete": delete,
        },
    )

    result = state.absent(
        "node1",
        confirm=True,
        drain=True,
        task_timeout=0.5,
        task_interval=0.1,
    )

    assert result["result"] is False
    assert "still has service instances" in result["comment"]
    delete.assert_not_called()


def test_absent_drain_fails_closed_without_requested_service_instances(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_host.list": Mock(return_value=envelope([host()])),
            "ceph_host.drain": Mock(return_value=envelope(status=204)),
            "ceph_host.delete": delete,
        },
    )

    result = state.absent("node1", confirm=True, drain=True)

    assert result["result"] is False
    assert "omitted requested service instance data" in result["comment"]
    delete.assert_not_called()


def test_absent_rejects_non_boolean_drain_before_mutation(monkeypatch):
    drain = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(), "ceph_host.drain": drain},
    )

    result = state.absent("node1", confirm=True, drain="yes")

    assert result["result"] is False
    assert "drain must be a boolean" in result["comment"]
    drain.assert_not_called()


def test_absent_is_idempotent(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_host.list": Mock(return_value=envelope([])), "ceph_host.delete": delete},
    )
    assert state.absent("node1")["result"] is True
    delete.assert_not_called()
