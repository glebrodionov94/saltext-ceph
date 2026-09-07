"""Declarative RGW IAM/account state tests."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_rgw_iam as state

ACCOUNT_ID = "RGW11111111111111111"


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def account(**changes):
    value = {
        "id": ACCOUNT_ID,
        "name": "team",
        "tenant": "tenant-a",
        "email": "team@example.test",
        "max_buckets": 100,
        "max_users": 20,
        "max_roles": 30,
        "max_groups": 40,
        "max_access_keys": 4,
        "quota": {"enabled": False, "max_size": -1, "max_objects": -1},
        "bucket_quota": {"enabled": False, "max_size": -1, "max_objects": -1},
    }
    value.update(changes)
    return value


def role(**changes):
    value = {
        "RoleName": "backup",
        "Path": "/service/",
        "AssumeRolePolicyDocument": '{"Statement":[]}',
        "MaxSessionDuration": 3600,
        "PermissionPolicies": [],
    }
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_account_present_is_idempotent(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_iam.list_accounts": Mock(return_value=envelope([account()])),
            "ceph_rgw_iam.update_account": update,
        },
    )
    result = state.account_present(
        "team",
        account_id=ACCOUNT_ID,
        tenant="tenant-a",
        email="team@example.test",
        max_buckets=100,
    )
    assert result["result"] is True
    update.assert_not_called()


def test_account_present_creates_and_discovers_generated_id(monkeypatch):
    listing = Mock(side_effect=[envelope([]), envelope([account()])])
    create = Mock(return_value=envelope(account(), status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_iam.list_accounts": listing, "ceph_rgw_iam.create_account": create},
    )
    result = state.account_present("team", tenant="tenant-a")
    assert result["result"] is True
    create.assert_called_once()


def test_account_present_refuses_to_recreate_missing_pinned_id(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_iam.list_accounts": Mock(return_value=envelope([]))},
    )
    result = state.account_present("team", account_id=ACCOUNT_ID)
    assert result["result"] is False
    assert "generates IDs" in result["comment"]


def test_account_present_rejects_clear_that_controller_ignores(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_iam.list_accounts": Mock(return_value=envelope([account()]))},
    )
    result = state.account_present("team", email="")
    assert result["result"] is False
    assert "cannot clear" in result["comment"]


def test_account_present_rejects_zero_limit_that_controller_ignores(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_iam.list_accounts": Mock(return_value=envelope([account()]))},
    )
    result = state.account_present("team", max_users=0)
    assert result["result"] is False
    assert "cannot set limits to zero" in result["comment"]


def test_account_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_iam.list_accounts": Mock(return_value=envelope([account()])),
            "ceph_rgw_iam.delete_account": delete,
        },
    )
    result = state.account_absent("team", account_id=ACCOUNT_ID)
    assert result["result"] is False
    delete.assert_not_called()


def test_account_quota_is_exact_for_decimal_bytes(monkeypatch):
    get = Mock(
        return_value=envelope(
            account(
                quota={
                    "enabled": True,
                    "max_size": 10737418240,
                    "max_size_kb": 10485760,
                    "max_objects": 1000000,
                }
            )
        )
    )
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_iam.get_account": get, "ceph_rgw_iam.set_account_quota": set_},
    )
    result = state.account_quota_present("account", ACCOUNT_ID, True, 10737418240, 1000000)
    assert result["result"] is True
    set_.assert_not_called()


def test_account_quota_disable_requires_confirmation(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_iam.get_account": Mock(
                return_value=envelope(
                    account(quota={"enabled": True, "max_size": 10, "max_objects": 2})
                )
            ),
            "ceph_rgw_iam.set_account_quota": Mock(),
        },
    )
    result = state.account_quota_present("account", ACCOUNT_ID, False, 10, 2)
    assert result["result"] is False
    assert "confirm_disable" in result["comment"]


def test_role_present_is_idempotent_with_semantic_policy(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_iam.list_roles": Mock(return_value=envelope([role()])),
            "ceph_rgw_iam.create_role": create,
        },
    )
    result = state.role_present(
        "backup",
        "/service/",
        role_assume_policy_doc={"Statement": []},
        max_session_duration=1,
    )
    assert result["result"] is True
    create.assert_not_called()


def test_role_present_updates_only_mutable_duration(monkeypatch):
    before = role(MaxSessionDuration=3600)
    after = role(MaxSessionDuration=7200)
    listing = Mock(side_effect=[envelope([before]), envelope([before]), envelope([after])])
    update = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_iam.list_roles": listing, "ceph_rgw_iam.update_role": update},
    )
    result = state.role_present("backup", "/service/", max_session_duration=2)
    assert result["result"] is True
    update.assert_called_once_with("backup", 2.0, account_id=None, profile="default")


def test_role_immutable_drift_requires_replace(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_iam.list_roles": Mock(return_value=envelope([role(Path="/old/")]))},
    )
    result = state.role_present("backup", "/service/")
    assert result["result"] is False
    assert "replace=True" in result["comment"]


def test_role_replace_deletes_creates_and_verifies(monkeypatch):
    before = role(Path="/old/")
    listing = Mock(side_effect=[envelope([before]), envelope([role()])])
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_iam.list_roles": listing,
            "ceph_rgw_iam.delete_role": delete,
            "ceph_rgw_iam.create_role": create,
        },
    )
    result = state.role_present("backup", "/service/", replace=True, confirm_replace=True)
    assert result["result"] is True
    delete.assert_called_once_with("backup", account_id=None, confirm=True, profile="default")
    create.assert_called_once()


def test_role_absent_requires_confirmation(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_iam.list_roles": Mock(return_value=envelope([role()])),
            "ceph_rgw_iam.delete_role": delete,
        },
    )
    result = state.role_absent("backup")
    assert result["result"] is False
    delete.assert_not_called()


def test_role_read_rejects_invalid_duration_instead_of_mutating(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_iam.list_roles": Mock(
                return_value=envelope([role(MaxSessionDuration="invalid")])
            ),
            "ceph_rgw_iam.update_role": update,
        },
    )
    result = state.role_present("backup", "/service/", max_session_duration=1)
    assert result["result"] is False
    assert "invalid MaxSessionDuration" in result["comment"]
    update.assert_not_called()
