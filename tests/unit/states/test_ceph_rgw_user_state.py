"""Declarative RGW user state tests."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_rgw_user as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def user(**changes):
    value = {
        "uid": "alice",
        "full_user_id": "alice",
        "display_name": "Alice",
        "email": "alice@example.test",
        "max_buckets": 100,
        "system": "false",
        "suspended": 0,
        "type": "rgw",
        "subusers": [],
        "caps": [],
    }
    value.update(changes)
    return value


def reads(users=None, details=None):
    users = ["alice"] if users is None else users
    details = user() if details is None else details
    return {
        "ceph_rgw_user.list_users": Mock(return_value=envelope(users)),
        "ceph_rgw_user.get_user": Mock(return_value=envelope(details)),
    }


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_virtual_reports_missing_execution_functions(monkeypatch):
    monkeypatch.setattr(state, "__salt__", {})
    result = state.__virtual__()
    assert result[0] is False
    assert "list_users" in result[1]


def test_present_is_idempotent_and_normalizes_admin_ops_booleans(monkeypatch):
    salt = reads()
    salt["ceph_rgw_user.update_user"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present(
        "alice",
        "Alice",
        email="alice@example.test",
        max_buckets=100,
        system=False,
        suspended=False,
    )
    assert result["result"] is True
    assert not result["changes"]
    salt["ceph_rgw_user.update_user"].assert_not_called()


@pytest.mark.parametrize("declared", ["saltext-ci-tenant/alice", "saltext-ci-tenant$alice"])
def test_present_is_idempotent_for_tenant_user_aliases(monkeypatch, declared):
    tenant_user = user(
        uid="alice",
        full_user_id="saltext-ci-tenant$alice",
        tenant="saltext-ci-tenant",
    )
    salt = reads(users=["saltext-ci-tenant$alice"], details=tenant_user)
    salt["ceph_rgw_user.update_user"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)

    result = state.present(declared, "Alice")

    assert result["result"] is True
    assert not result["changes"]
    salt["ceph_rgw_user.get_user"].assert_called_once_with(
        "saltext-ci-tenant$alice",
        daemon_name=None,
        stats=False,
        include_secrets=False,
        profile="default",
    )
    salt["ceph_rgw_user.update_user"].assert_not_called()


def test_present_rejects_tenant_response_for_different_full_user(monkeypatch):
    tenant_user = user(
        uid="alice",
        full_user_id="other-tenant$alice",
        tenant="other-tenant",
    )
    salt = reads(users=["saltext-ci-tenant$alice"], details=tenant_user)
    monkeypatch.setattr(state, "__salt__", salt)

    result = state.present("saltext-ci-tenant$alice", "Alice")

    assert result["result"] is False
    assert "different user" in result["comment"]


def test_present_plans_creation_without_exposing_secret_source(monkeypatch, tmp_path):
    secret = tmp_path / "secret"
    secret.write_text("top-secret", encoding="utf-8")
    salt = reads(users=[])
    salt["ceph_rgw_user.create_user"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    monkeypatch.setattr(state, "__opts__", {"test": True})
    result = state.present("alice", "Alice", secret_key_source=str(secret))
    assert result["result"] is None
    assert "top-secret" not in str(result)
    assert "secret" not in result["changes"]["new"]
    salt["ceph_rgw_user.create_user"].assert_not_called()


def test_present_creates_waits_and_post_reads(monkeypatch):
    listing = Mock(side_effect=[envelope([]), envelope(["alice"])])
    create = Mock(
        return_value=envelope({"name": "rgw/user/create", "metadata": {"uid": "alice"}}, 202)
    )
    wait = Mock(return_value=envelope({"success": True}))
    salt = {
        "ceph_rgw_user.list_users": listing,
        "ceph_rgw_user.get_user": Mock(return_value=envelope(user())),
        "ceph_rgw_user.create_user": create,
        "ceph_task.wait": wait,
    }
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present("alice", "Alice", email="alice@example.test", max_buckets=100)
    assert result["result"] is True
    create.assert_called_once()
    assert create.call_args.kwargs["include_secrets"] is False
    wait.assert_called_once()


def test_present_rejects_tenant_creation_before_mutation(monkeypatch):
    salt = reads(users=[])
    salt["ceph_rgw_user.create_user"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)

    result = state.present("saltext-ci-tenant/alice", "Alice")

    assert result["result"] is False
    assert "cannot create tenant" in result["comment"]
    salt["ceph_rgw_user.create_user"].assert_not_called()


def test_present_updates_only_readable_fields(monkeypatch):
    before = user(display_name="Old")
    salt = reads(details=before)
    salt["ceph_rgw_user.list_users"].side_effect = [
        envelope(["alice"]),
        envelope(["alice"]),
    ]
    salt["ceph_rgw_user.get_user"].side_effect = [
        envelope(before),
        envelope(user()),
    ]
    salt["ceph_rgw_user.update_user"] = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present("alice", "Alice")
    assert result["result"] is True
    assert salt["ceph_rgw_user.update_user"].call_args.kwargs["display_name"] == "Alice"


def test_present_rejects_root_demotion(monkeypatch):
    salt = reads(details=user(type="root"))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present("alice", "Alice", account_root_user=False)
    assert result["result"] is False
    assert "demote" in result["comment"]


def test_absent_requires_confirmation_and_then_verifies(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    salt = reads()
    salt["ceph_rgw_user.delete_user"] = delete
    monkeypatch.setattr(state, "__salt__", salt)
    assert state.absent("alice")["result"] is False
    delete.assert_not_called()
    salt["ceph_rgw_user.list_users"].side_effect = [envelope(["alice"]), envelope([])]
    result = state.absent("alice", confirm=True)
    assert result["result"] is True
    delete.assert_called_once_with("alice", daemon_name=None, confirm=True, profile="default")


def test_subuser_update_never_rotates_credentials(monkeypatch):
    before = user(subusers=[{"id": "alice:swift", "permissions": "read"}])
    after = user(subusers=[{"id": "alice:swift", "permissions": "read-write"}])
    salt = reads(details=before)
    salt["ceph_rgw_user.list_users"].side_effect = [
        envelope(["alice"]),
        envelope(["alice"]),
    ]
    salt["ceph_rgw_user.get_user"].side_effect = [envelope(before), envelope(after)]
    salt["ceph_rgw_user.create_subuser"] = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.subuser_present("swift", "alice", "readwrite")
    assert result["result"] is True
    assert salt["ceph_rgw_user.create_subuser"].call_args.args[1] == "alice:swift"
    kwargs = salt["ceph_rgw_user.create_subuser"].call_args.kwargs
    assert kwargs["generate_secret"] is False
    assert kwargs["access_key_source"] is None
    assert kwargs["secret_key_source"] is None


def test_subuser_present_creates_then_post_reads(monkeypatch):
    after = user(subusers=[{"id": "alice:swift", "permissions": "read"}])
    salt = reads()
    salt["ceph_rgw_user.list_users"].side_effect = [
        envelope(["alice"]),
        envelope(["alice"]),
    ]
    salt["ceph_rgw_user.get_user"].side_effect = [envelope(user()), envelope(after)]
    salt["ceph_rgw_user.create_subuser"] = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(state, "__salt__", salt)

    result = state.subuser_present("swift", "alice", "read", key_type="swift")

    assert result["result"] is True
    kwargs = salt["ceph_rgw_user.create_subuser"].call_args.kwargs
    assert kwargs["generate_secret"] is True
    assert kwargs["key_type"] == "swift"


def test_subuser_present_is_idempotent(monkeypatch):
    current = user(subusers=[{"id": "alice:swift", "permissions": "read-write"}])
    salt = reads(details=current)
    salt["ceph_rgw_user.create_subuser"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)

    result = state.subuser_present("swift", "alice", "readwrite", key_type="swift")

    assert result["result"] is True
    assert not result["changes"]
    salt["ceph_rgw_user.create_subuser"].assert_not_called()


def test_subuser_delete_requires_confirm(monkeypatch):
    current = user(subusers=[{"id": "alice:swift", "permissions": "full-control"}])
    salt = reads(details=current)
    salt["ceph_rgw_user.delete_subuser"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.subuser_absent("swift", "alice")
    assert result["result"] is False
    salt["ceph_rgw_user.delete_subuser"].assert_not_called()


def test_subuser_delete_confirms_and_post_reads(monkeypatch):
    before = user(subusers=[{"id": "alice:swift", "permissions": "full-control"}])
    salt = reads(details=before)
    salt["ceph_rgw_user.list_users"].side_effect = [
        envelope(["alice"]),
        envelope(["alice"]),
    ]
    salt["ceph_rgw_user.get_user"].side_effect = [envelope(before), envelope(user())]
    salt["ceph_rgw_user.delete_subuser"] = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(state, "__salt__", salt)

    result = state.subuser_absent("swift", "alice", confirm=True)

    assert result["result"] is True
    salt["ceph_rgw_user.delete_subuser"].assert_called_once_with(
        "alice",
        "alice:swift",
        purge_keys=True,
        daemon_name=None,
        confirm=True,
        profile="default",
    )


def test_capability_create_and_postcondition(monkeypatch):
    after = user(caps=[{"type": "buckets", "perm": "write, read"}])
    salt = reads()
    salt["ceph_rgw_user.list_users"].side_effect = [
        envelope(["alice"]),
        envelope(["alice"]),
    ]
    salt["ceph_rgw_user.get_user"].side_effect = [envelope(user()), envelope(after)]
    salt["ceph_rgw_user.create_capability"] = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.capability_present("buckets", "alice", "read,write")
    assert result["result"] is True


def test_capability_permission_drift_requires_confirmed_replace(monkeypatch):
    before = user(caps=[{"type": "buckets", "perm": "read"}])
    after = user(caps=[{"type": "buckets", "perm": "read,write"}])
    salt = reads(details=before)
    salt["ceph_rgw_user.delete_capability"] = Mock(return_value=envelope(status=204))
    salt["ceph_rgw_user.create_capability"] = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.capability_present("buckets", "alice", "read,write")
    assert result["result"] is False
    assert "replace=True" in result["comment"]
    salt["ceph_rgw_user.delete_capability"].assert_not_called()

    salt["ceph_rgw_user.list_users"].side_effect = [
        envelope(["alice"]),
        envelope(["alice"]),
    ]
    salt["ceph_rgw_user.get_user"].side_effect = [envelope(before), envelope(after)]
    result = state.capability_present(
        "buckets", "alice", "read,write", replace=True, confirm_replace=True
    )
    assert result["result"] is True
    salt["ceph_rgw_user.delete_capability"].assert_called_once_with(
        "alice", "buckets", "read", daemon_name=None, confirm=True, profile="default"
    )


def test_capability_rejects_ambiguous_permission_list(monkeypatch):
    monkeypatch.setattr(state, "__salt__", reads())
    result = state.capability_present("buckets", "alice", "read,,write")
    assert result["result"] is False
    assert "empty or duplicate" in result["comment"]


def test_quota_disable_requires_explicit_confirmation(monkeypatch):
    salt = {
        "ceph_rgw_user.get_quota": Mock(
            return_value=envelope(
                {
                    "user_quota": {
                        "enabled": True,
                        "max_size_kb": 1024,
                        "max_objects": 10,
                    }
                }
            )
        ),
        "ceph_rgw_user.set_quota": Mock(),
    }
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.quota_present("user", "alice", False, 1024, 10)
    assert result["result"] is False
    assert "confirm_disable" in result["comment"]


def test_quota_updates_and_post_reads(monkeypatch):
    quota = Mock(
        side_effect=[
            envelope({"bucket_quota": {"enabled": False, "max_size_kb": 0, "max_objects": -1}}),
            envelope({"bucket_quota": {"enabled": True, "max_size_kb": 2048, "max_objects": 20}}),
        ]
    )
    set_ = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_user.get_quota": quota, "ceph_rgw_user.set_quota": set_},
    )
    result = state.quota_present("bucket", "alice", True, 2048, 20)
    assert result["result"] is True
    set_.assert_called_once()


def test_rate_limit_accepts_nested_admin_ops_shape(monkeypatch):
    current = {
        "user_ratelimit": {
            "enabled": True,
            "max_read_ops": 10,
            "max_write_ops": 20,
            "max_read_bytes": 30,
            "max_write_bytes": 40,
        }
    }
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_user.get_rate_limit": Mock(return_value=envelope(current)),
            "ceph_rgw_user.set_rate_limit": set_,
        },
    )
    result = state.rate_limit_present("alice", True, 10, 20, 30, 40)
    assert result["result"] is True
    set_.assert_not_called()


def test_managed_policies_require_confirmation_for_detach(monkeypatch):
    current = user(
        account_id="RGW11111111111111111",
        managed_user_policies=[{"PolicyArn": "arn:old"}, {"PolicyArn": "arn:keep"}],
    )
    salt = reads(details=current)
    salt["ceph_rgw_user.update_user"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.managed_policies_present("alice", ["arn:keep"])
    assert result["result"] is False
    assert "confirm_remove" in result["comment"]
    salt["ceph_rgw_user.update_user"].assert_not_called()


def test_managed_policies_compute_attach_and_detach(monkeypatch):
    before = user(managed_user_policies=["arn:old"])
    after = user(managed_user_policies=["arn:new"])
    salt = reads(details=before)
    salt["ceph_rgw_user.list_users"].side_effect = [
        envelope(["alice"]),
        envelope(["alice"]),
    ]
    salt["ceph_rgw_user.get_user"].side_effect = [envelope(before), envelope(after)]
    salt["ceph_rgw_user.update_user"] = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.managed_policies_present("alice", ["arn:new"], confirm_remove=True)
    assert result["result"] is True
    kwargs = salt["ceph_rgw_user.update_user"].call_args.kwargs
    assert kwargs["account_policies"] == {"attach": ["arn:new"], "detach": ["arn:old"]}
    assert kwargs["confirm_policy_detach"] is True
