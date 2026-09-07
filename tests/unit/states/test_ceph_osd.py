"""OSD state reconciliation."""

from unittest.mock import Mock

import pytest
from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.states import ceph_osd as state
from saltext.ceph.utils.ceph.errors import APIError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import TaskFailedError
from saltext.ceph.utils.ceph.errors import TransportError


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def item(device_class="hdd"):
    return {"id": 1, "tree": {"device_class": device_class}, "state": ["up", "in"]}


def flag_item(*flags):
    return {"osd": 1, "flags": list(flags or ("up", "in"))}


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_device_class_is_idempotent(monkeypatch):
    set_class = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.set_device_class": set_class,
        },
    )
    assert state.device_class_managed(1, "hdd")["result"] is True
    set_class.assert_not_called()


def test_device_class_changes_and_verifies(monkeypatch):
    list_ = Mock(side_effect=[envelope([item()]), envelope([item("ssd")])])
    set_class = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.list": list_, "ceph_osd.set_device_class": set_class},
    )
    result = state.device_class_managed(1, "ssd")
    assert result["result"] is True
    set_class.assert_called_once_with(1, "ssd", profile="default")


def test_cluster_flags_preserve_non_removable_current_flags(monkeypatch):
    flags = Mock(
        side_effect=[envelope(["sortbitwise", "noout"]), envelope(["sortbitwise", "noup"])]
    )
    set_flags = Mock(return_value=envelope(status=200, data=["sortbitwise", "noup"]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.flags": flags, "ceph_osd.set_flags": set_flags},
    )
    result = state.flags_managed("cluster", ["noup"])
    assert result["result"] is True
    set_flags.assert_called_once_with(["noup", "sortbitwise"], profile="default")


def test_cluster_flags_plan_never_mutates(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    set_flags = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.flags": Mock(return_value=envelope([])), "ceph_osd.set_flags": set_flags},
    )
    assert state.flags_managed("cluster", ["noout"])["result"] is None
    set_flags.assert_not_called()


def test_cluster_flags_reject_impossible_purged_snapshots(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.flags": Mock(return_value=envelope([]))},
    )
    result = state.flags_managed("cluster", ["purged_snapshots"])
    assert result["result"] is False


def test_individual_flags_are_idempotent(monkeypatch):
    set_flags = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.individual_flags": Mock(
                return_value=envelope([{"osd": 1, "flags": ["up", "noout"]}])
            ),
            "ceph_osd.set_individual_flags": set_flags,
        },
    )
    assert state.individual_flags_managed("maintenance", [1], {"noout": True})["result"] is True
    set_flags.assert_not_called()


def test_individual_flags_change_and_verify(monkeypatch):
    read = Mock(
        side_effect=[
            envelope([{"osd": 1, "flags": ["up"]}]),
            envelope([{"osd": 1, "flags": ["up", "noout"]}]),
        ]
    )
    set_flags = Mock(return_value=envelope(status=200, data={}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.individual_flags": read, "ceph_osd.set_individual_flags": set_flags},
    )
    result = state.individual_flags_managed("maintenance", [1], {"noout": True})
    assert result["result"] is True
    set_flags.assert_called_once_with({"noout": True}, [1], profile="default")


def test_absent_checks_safety_then_removes(monkeypatch):
    list_ = Mock(side_effect=[envelope([item()]), envelope([])])
    remove = Mock(return_value=envelope({"name": "osd/delete", "metadata": {"svc_id": "1"}}, 202))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": list_,
            "ceph_osd.individual_flags": Mock(return_value=envelope([])),
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": remove,
            "ceph_task.wait": wait,
        },
    )
    result = state.absent(1, confirm=True)
    assert result["result"] is True
    remove.assert_called_once_with(
        1, preserve_id=False, force=False, confirm=True, profile="default"
    )
    wait.assert_called_once()


def test_absent_polls_past_a_stale_read_after_successful_removal(monkeypatch):
    list_ = Mock(return_value=envelope([item()]))
    presence = Mock(side_effect=[envelope([flag_item()]), envelope([])])
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": list_,
            "ceph_osd.individual_flags": presence,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": Mock(return_value=envelope(status=204)),
        },
    )

    result = state.absent(1, confirm=True, task_timeout=5.0, task_interval=1.0)

    assert result["result"] is True
    assert result["changes"] == {"old": item(), "new": None}
    assert result["comment"] == "OSD 1 was removed."
    list_.assert_called_once()
    assert presence.call_count == 2
    sleep.assert_called_once_with(1.0)


def test_absent_succeeds_when_task_errors_but_osd_converges_to_absent(monkeypatch):
    list_ = Mock(return_value=envelope([item()]))
    presence = Mock(
        side_effect=[
            TransportError("temporary OSD presence failure"),
            envelope([flag_item()]),
            envelope([]),
        ]
    )
    wait = Mock(side_effect=TaskFailedError("original asynchronous removal failure"))
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0, 0.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": list_,
            "ceph_osd.individual_flags": presence,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": Mock(
                return_value=envelope({"name": "osd/delete", "metadata": {"svc_id": "1"}}, 202)
            ),
            "ceph_task.wait": wait,
        },
    )

    result = state.absent(1, confirm=True, task_timeout=5.0, task_interval=1.0)

    assert result["result"] is True
    assert result["changes"] == {"old": item(), "new": None}
    assert "removal operation reported an error" in result["comment"]
    assert "confirmed its absence" in result["comment"]
    list_.assert_called_once()
    assert presence.call_count == 3
    wait.assert_called_once()
    assert sleep.call_args_list == [((1.0,),), ((1.0,),)]


def test_absent_preserves_task_and_repeated_read_errors(monkeypatch):
    list_ = Mock(return_value=envelope([item()]))
    presence = Mock(
        side_effect=[
            TransportError("first OSD presence failure"),
            TransportError("last OSD presence failure"),
        ]
    )
    wait = Mock(side_effect=TaskFailedError("original asynchronous removal failure"))
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0, 1.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": list_,
            "ceph_osd.individual_flags": presence,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": Mock(
                return_value=envelope({"name": "osd/delete", "metadata": {"svc_id": "1"}}, 202)
            ),
            "ceph_task.wait": wait,
        },
    )

    result = state.absent(1, confirm=True, task_timeout=0.5, task_interval=0.1)

    assert result["result"] is False
    assert "TaskFailedError: original asynchronous removal failure" in result["comment"]
    assert "OSD 1 absence was not confirmed before timeout." in result["comment"]
    assert "TransportError: last OSD presence failure" in result["comment"]
    assert "first OSD presence failure" not in result["comment"]
    list_.assert_called_once()
    assert presence.call_count == 2
    wait.assert_called_once()
    sleep.assert_called_once_with(0.1)


def test_absent_preserves_repeated_read_error_after_successful_mutation(monkeypatch):
    list_ = Mock(return_value=envelope([item()]))
    presence = Mock(
        side_effect=[
            TransportError("first OSD presence failure"),
            TransportError("last OSD presence failure"),
        ]
    )
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0, 1.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": list_,
            "ceph_osd.individual_flags": presence,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": Mock(return_value=envelope(status=204)),
        },
    )

    result = state.absent(1, confirm=True, task_timeout=0.5, task_interval=0.1)

    assert result["result"] is False
    assert "OSD 1 absence was not confirmed before timeout." in result["comment"]
    assert "TransportError: last OSD presence failure" in result["comment"]
    assert "first OSD presence failure" not in result["comment"]
    assert "removal reported" not in result["comment"]
    list_.assert_called_once()
    assert presence.call_count == 2
    sleep.assert_called_once_with(0.1)


def test_absent_preserves_mutation_error_when_osd_remains(monkeypatch):
    list_ = Mock(return_value=envelope([item()]))
    presence = Mock(return_value=envelope([flag_item()]))
    remove = Mock(side_effect=TransportError("original mutation failure"))
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 1.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": list_,
            "ceph_osd.individual_flags": presence,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1, confirm=True, task_timeout=0.5, task_interval=0.1)

    assert result["result"] is False
    assert not result["changes"]
    assert "TransportError: original mutation failure" in result["comment"]
    assert "OSD 1 still exists after removal." in result["comment"]
    list_.assert_called_once()
    presence.assert_called_once()
    remove.assert_called_once()
    sleep.assert_not_called()


@pytest.mark.parametrize("status", (400, 401))
@pytest.mark.parametrize("wrapped", (False, True), ids=("api-error", "salt-error"))
def test_absent_fails_fast_for_definitive_http_client_errors(monkeypatch, status, wrapped):
    error = (
        CommandExecutionError(str(APIError(status)), info={"status": status})
        if wrapped
        else APIError(status)
    )
    presence = Mock()
    wait_for_absence = Mock()
    monkeypatch.setattr(state, "_wait_for_absence", wait_for_absence)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.individual_flags": presence,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": Mock(side_effect=error),
        },
    )

    result = state.absent(1, confirm=True)

    assert result["result"] is False
    assert f"HTTP {status}" in result["comment"]
    presence.assert_not_called()
    wait_for_absence.assert_not_called()


@pytest.mark.parametrize(
    "error",
    (ConfigurationError("invalid removal request"), SaltInvocationError("invalid invocation")),
    ids=("configuration", "salt-invocation"),
)
def test_absent_fails_fast_for_local_removal_validation(monkeypatch, error):
    wait_for_absence = Mock()
    monkeypatch.setattr(state, "_wait_for_absence", wait_for_absence)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": Mock(side_effect=error),
        },
    )

    result = state.absent(1, confirm=True)

    assert result["result"] is False
    assert result["comment"] == str(error)
    wait_for_absence.assert_not_called()


def test_absent_verifies_after_server_error_that_may_have_applied(monkeypatch):
    presence = Mock(return_value=envelope([]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.individual_flags": presence,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": Mock(side_effect=APIError(500)),
        },
    )

    result = state.absent(1, confirm=True)

    assert result["result"] is True
    assert result["changes"] == {"old": item(), "new": None}
    assert "removal operation reported an error" in result["comment"]
    presence.assert_called_once_with(profile="default")


def test_absent_uses_osd_map_presence_when_detailed_list_is_broken(monkeypatch):
    presence = Mock(side_effect=[envelope([flag_item()]), envelope([])])
    remove = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(side_effect=TransportError("OSD list controller failed")),
            "ceph_osd.individual_flags": presence,
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1, confirm=True)

    assert result["result"] is True
    assert result["changes"] == {"old": {"id": 1, "state": ["up", "in"]}, "new": None}
    assert presence.call_count == 2
    remove.assert_called_once()


def test_absent_is_idempotent_when_list_is_broken_but_osd_map_confirms_absence(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(side_effect=TransportError("OSD list controller failed")),
            "ceph_osd.individual_flags": Mock(return_value=envelope([])),
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1)

    assert result["result"] is True
    assert result["comment"] == "OSD 1 is already absent."
    remove.assert_not_called()


def test_absent_checks_osd_map_after_clean_detailed_list_miss(monkeypatch):
    presence = Mock(return_value=envelope([flag_item()]))
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([])),
            "ceph_osd.individual_flags": presence,
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1)

    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    presence.assert_called_once_with(profile="default")
    remove.assert_not_called()


def test_absent_fails_closed_when_osd_map_read_fails_after_clean_list_miss(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([])),
            "ceph_osd.individual_flags": Mock(
                side_effect=TransportError("OSD map presence failed")
            ),
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1)

    assert result["result"] is False
    assert result["comment"] == "OSD map presence failed"
    remove.assert_not_called()


def test_absent_preserves_both_initial_presence_read_errors(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(side_effect=TransportError("OSD list controller failed")),
            "ceph_osd.individual_flags": Mock(
                side_effect=TransportError("OSD map presence failed")
            ),
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1)

    assert result["result"] is False
    assert "TransportError: OSD list controller failed" in result["comment"]
    assert "TransportError: OSD map presence failed" in result["comment"]
    remove.assert_not_called()


def test_absent_does_not_treat_a_malformed_presence_read_as_absence(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 1.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.individual_flags": Mock(return_value=envelope([{"osd": 1, "flags": "up"}])),
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": Mock(return_value=envelope(status=204)),
        },
    )

    result = state.absent(1, confirm=True, task_timeout=0.5, task_interval=0.1)

    assert result["result"] is False
    assert "unexpected shape" in result["comment"]
    sleep.assert_not_called()


def test_absent_with_preserved_id_converges_on_destroyed_osd(monkeypatch):
    remove = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.individual_flags": Mock(return_value=envelope([flag_item("destroyed")])),
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": True})),
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1, preserve_id=True, confirm=True)

    assert result["result"] is True
    assert result["changes"]["new"] == {"id": 1, "state": ["destroyed"]}
    assert "ID was preserved" in result["comment"]
    remove.assert_called_once_with(
        1, preserve_id=True, force=False, confirm=True, profile="default"
    )


def test_absent_with_preserved_id_is_idempotent_for_destroyed_osd(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([{"id": 1, "state": ["destroyed"]}])),
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1, preserve_id=True)

    assert result["result"] is True
    assert result["comment"] == "OSD 1 is already removed and its ID is preserved."
    remove.assert_not_called()


def test_absent_with_preserved_id_reports_destroyed_plan(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.remove": remove,
        },
    )

    result = state.absent(1, preserve_id=True)

    assert result["result"] is None
    assert result["changes"]["new"] == {"id": 1, "state": ["destroyed"]}
    assert "ID preserved" in result["comment"]
    remove.assert_not_called()


def test_absent_refuses_unsafe_osd(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.safe_to_delete": Mock(return_value=envelope({"is_safe_to_delete": False})),
            "ceph_osd.remove": remove,
        },
    )
    result = state.absent(1, confirm=True)
    assert result["result"] is False
    remove.assert_not_called()


def test_absent_force_skips_preflight_but_requires_confirmation(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_osd.list": Mock(return_value=envelope([item()])), "ceph_osd.remove": remove},
    )
    assert state.absent(1, force=True)["result"] is False
    remove.assert_not_called()


def test_absent_test_mode_plans_without_safety_or_confirmation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    safety = Mock()
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([item()])),
            "ceph_osd.safe_to_delete": safety,
            "ceph_osd.remove": remove,
        },
    )
    assert state.absent(1)["result"] is None
    safety.assert_not_called()
    remove.assert_not_called()


def test_absent_is_idempotent(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_osd.list": Mock(return_value=envelope([])),
            "ceph_osd.individual_flags": Mock(return_value=envelope([])),
            "ceph_osd.remove": remove,
        },
    )
    assert state.absent(1)["result"] is True
    remove.assert_not_called()
