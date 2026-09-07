"""Dashboard role state reconciliation."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_role as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def resource(
    description="Backup operators",
    scopes_permissions=None,
    system=False,
):
    return {
        "name": "backup-manager",
        "description": description,
        "scopes_permissions": (
            {"pool": ["read", "create"]} if scopes_permissions is None else scopes_permissions
        ),
        "system": system,
    }


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_virtual_requires_all_execution_functions(monkeypatch):
    assert state.__virtual__()[0] is False
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_role.list": Mock(),
            "ceph_role.create": Mock(),
            "ceph_role.update": Mock(),
            "ceph_role.delete": Mock(),
        },
    )
    assert state.__virtual__() == "ceph_role"


def test_present_is_idempotent_and_permission_order_is_irrelevant(monkeypatch):
    create = Mock()
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_role.list": Mock(return_value=envelope([resource()])),
            "ceph_role.create": create,
            "ceph_role.update": update,
        },
    )
    result = state.present(
        "backup-manager",
        description="Backup operators",
        scopes_permissions={"pool": ["create", "read"]},
    )
    assert result["result"] is True
    assert not result["changes"]
    create.assert_not_called()
    update.assert_not_called()


def test_empty_permission_lists_have_server_canonical_empty_mapping(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_role.list": Mock(
                return_value=envelope([resource(description=None, scopes_permissions={})])
            ),
            "ceph_role.update": update,
        },
    )
    result = state.present("backup-manager", scopes_permissions={"pool": []})
    assert result["result"] is True
    update.assert_not_called()


def test_present_plans_exact_create_without_mutating(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_role.list": Mock(return_value=envelope([])), "ceph_role.create": create},
    )
    result = state.present(
        "backup-manager",
        description="Backup operators",
        scopes_permissions={"pool": ["read"]},
    )
    assert result["result"] is None
    assert result["changes"]["old"] is None
    assert result["changes"]["new"]["scopes_permissions"] == {"pool": ["read"]}
    create.assert_not_called()


def test_present_creates_waits_for_202_and_post_reads(monkeypatch):
    after = resource(scopes_permissions={"pool": ["read"]})
    list_ = Mock(side_effect=[envelope([]), envelope([after])])
    create = Mock(
        return_value=envelope({"name": "role/create", "metadata": {"name": "backup-manager"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_role.list": list_,
            "ceph_role.create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.present(
        "backup-manager",
        description="Backup operators",
        scopes_permissions={"pool": ["read"]},
    )
    assert result["result"] is True
    create.assert_called_once_with(
        "backup-manager",
        description="Backup operators",
        scopes_permissions={"pool": ["read"]},
        profile="default",
    )
    wait.assert_called_once()
    assert list_.call_count == 2


def test_present_updates_and_reports_only_managed_projection(monkeypatch):
    before = resource(description="Old", scopes_permissions={"pool": ["read"]})
    after = resource(description="New", scopes_permissions={"pool": ["read"]})
    update = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_role.list": Mock(side_effect=[envelope([before]), envelope([after])]),
            "ceph_role.update": update,
        },
    )
    result = state.present(
        "backup-manager", description="New", scopes_permissions={"pool": ["read"]}
    )
    assert result["changes"]["old"]["description"] == "Old"
    assert "system" not in result["changes"]["new"]
    update.assert_called_once()


@pytest.mark.parametrize("operation", ("present", "absent"))
def test_system_role_mutation_is_guarded_even_in_test_mode(monkeypatch, operation):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    mutation = Mock()
    built_in = resource(description="Built in", system=True)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_role.list": Mock(return_value=envelope([built_in])),
            "ceph_role.update": mutation,
            "ceph_role.delete": mutation,
        },
    )
    if operation == "present":
        result = state.present("backup-manager", description="Changed")
    else:
        result = state.absent("backup-manager", confirm=True)
    assert result["result"] is False
    assert "Built-in" in result["comment"]
    mutation.assert_not_called()


def test_absent_test_mode_plans_without_confirmation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_role.list": Mock(return_value=envelope([resource()])), "ceph_role.delete": delete},
    )
    result = state.absent("backup-manager")
    assert result["result"] is None
    assert result["changes"]["new"] is None
    delete.assert_not_called()


def test_absent_requires_confirmation_then_deletes_and_verifies(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    list_ = Mock(side_effect=[envelope([resource()]), envelope([resource()]), envelope([])])
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_role.list": list_, "ceph_role.delete": delete},
    )
    assert state.absent("backup-manager")["result"] is False
    delete.assert_not_called()
    result = state.absent("backup-manager", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with("backup-manager", confirm=True, profile="default")


def test_failed_post_read_is_a_state_failure(monkeypatch):
    before = resource(description="Old")
    update = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_role.list": Mock(return_value=envelope([before])),
            "ceph_role.update": update,
        },
    )
    result = state.present("backup-manager", description="New")
    assert result["result"] is False
    assert "did not converge" in result["comment"]
