"""Declarative RGW bucket state tests."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import ceph_rgw_bucket as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def bucket(**changes):
    value = {
        "bid": "data",
        "bucket": "data",
        "tenant": "",
        "id": "data.123",
        "owner": "alice",
        "versioning": "Suspended",
        "lock_enabled": False,
        "lock_mode": None,
        "lock_retention_period_days": None,
        "lock_retention_period_years": None,
        "bucket_policy": {},
        "replication": {
            "sync_policy_active": False,
            "replication_rules_configured": False,
            "policy": {},
        },
    }
    value.update(changes)
    return value


def bucket_reads(values=None, details=None):
    values = ["data"] if values is None else values
    details = bucket() if details is None else details
    return {
        "ceph_rgw_bucket.list_buckets": Mock(return_value=envelope(values)),
        "ceph_rgw_bucket.get_bucket": Mock(return_value=envelope(details)),
    }


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_present_is_idempotent_for_owner_and_lock(monkeypatch):
    salt = bucket_reads()
    salt["ceph_rgw_bucket.update_bucket"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present("data", "alice", lock_enabled=False)
    assert result["result"] is True
    salt["ceph_rgw_bucket.update_bucket"].assert_not_called()


def test_present_creates_with_creation_only_placement(monkeypatch):
    listing = Mock(side_effect=[envelope([]), envelope(["data"])])
    create = Mock(return_value=envelope(status=201))
    salt = {
        "ceph_rgw_bucket.list_buckets": listing,
        "ceph_rgw_bucket.get_bucket": Mock(return_value=envelope(bucket())),
        "ceph_rgw_bucket.create_bucket": create,
    }
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present("data", "alice", zonegroup="zg", placement_target="cold")
    assert result["result"] is True
    assert create.call_args.kwargs["zonegroup"] == "zg"
    assert "zonegroup" not in result["changes"]["new"]


def test_present_rejects_object_lock_enablement_drift(monkeypatch):
    monkeypatch.setattr(state, "__salt__", bucket_reads())
    result = state.present("data", "alice", lock_enabled=True, lock_mode="GOVERNANCE")
    assert result["result"] is False
    assert "immutable" in result["comment"]


def test_present_updates_owner_and_post_reads(monkeypatch):
    before = bucket(owner="bob")
    salt = bucket_reads(details=before)
    salt["ceph_rgw_bucket.list_buckets"].side_effect = [
        envelope(["data"]),
        envelope(["data"]),
    ]
    salt["ceph_rgw_bucket.get_bucket"].side_effect = [
        envelope(before),
        envelope(bucket()),
    ]
    salt["ceph_rgw_bucket.update_bucket"] = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present("data", "alice", confirm_owner_change=True)
    assert result["result"] is True
    assert salt["ceph_rgw_bucket.update_bucket"].call_args.kwargs["uid"] == "alice"


def test_present_requires_confirmation_for_owner_change(monkeypatch):
    salt = bucket_reads(details=bucket(owner="bob"))
    salt["ceph_rgw_bucket.update_bucket"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.present("data", "alice")
    assert result["result"] is False
    assert "confirm_owner_change" in result["comment"]
    salt["ceph_rgw_bucket.update_bucket"].assert_not_called()


def test_absent_requires_confirmation(monkeypatch):
    salt = bucket_reads()
    salt["ceph_rgw_bucket.delete_bucket"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.absent("data")
    assert result["result"] is False
    salt["ceph_rgw_bucket.delete_bucket"].assert_not_called()


def test_versioning_suspend_requires_confirmation(monkeypatch):
    salt = bucket_reads(details=bucket(versioning="Enabled"))
    salt["ceph_rgw_bucket.update_bucket"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.versioning_present("data", "Suspended")
    assert result["result"] is False
    assert "confirm_suspend" in result["comment"]


def test_versioning_updates_and_post_reads(monkeypatch):
    before = bucket(versioning="Suspended")
    after = bucket(versioning="Enabled")
    salt = bucket_reads(details=before)
    salt["ceph_rgw_bucket.list_buckets"].side_effect = [
        envelope(["data"]),
        envelope(["data"]),
    ]
    salt["ceph_rgw_bucket.get_bucket"].side_effect = [envelope(before), envelope(after)]
    salt["ceph_rgw_bucket.update_bucket"] = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.versioning_present("data", "Enabled")
    assert result["result"] is True


def test_versioning_plans_enablement_from_current_off_status(monkeypatch):
    salt = bucket_reads(details=bucket(versioning="Off"))
    salt["ceph_rgw_bucket.update_bucket"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    monkeypatch.setattr(state, "__opts__", {"test": True})

    result = state.versioning_present("data", "Enabled")

    assert result["result"] is None
    assert result["changes"] == {"old": "Off", "new": "Enabled"}
    salt["ceph_rgw_bucket.update_bucket"].assert_not_called()


def test_versioning_enables_current_off_status_and_verifies(monkeypatch):
    before = bucket(versioning="Off")
    after = bucket(versioning="Enabled")
    salt = bucket_reads(details=before)
    salt["ceph_rgw_bucket.list_buckets"].side_effect = [
        envelope(["data"]),
        envelope(["data"]),
    ]
    salt["ceph_rgw_bucket.get_bucket"].side_effect = [envelope(before), envelope(after)]
    salt["ceph_rgw_bucket.update_bucket"] = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(state, "__salt__", salt)

    result = state.versioning_present("data", "Enabled")

    assert result["result"] is True
    assert result["changes"] == {"old": "Off", "new": "Enabled"}
    assert salt["ceph_rgw_bucket.update_bucket"].call_args.kwargs["versioning_state"] == "Enabled"


def test_versioning_rejects_unknown_current_status(monkeypatch):
    salt = bucket_reads(details=bucket(versioning="Disabled"))
    salt["ceph_rgw_bucket.update_bucket"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)

    result = state.versioning_present("data", "Enabled")

    assert result["result"] is False
    assert "usable versioning status" in result["comment"]
    salt["ceph_rgw_bucket.update_bucket"].assert_not_called()


def test_encryption_reads_nested_s3_shape(monkeypatch):
    encryption = {
        "Status": "Enabled",
        "Rules": [
            {
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "aws:kms",
                    "KMSMasterKeyID": "key-1",
                }
            }
        ],
    }
    salt = bucket_reads()
    salt["ceph_rgw_bucket.get_encryption"] = Mock(return_value=envelope(encryption))
    salt["ceph_rgw_bucket.update_bucket"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.encryption_present("data", "kms", key_id="key-1")
    assert result["result"] is True
    salt["ceph_rgw_bucket.update_bucket"].assert_not_called()


def test_encryption_absent_requires_confirmation(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_bucket.get_encryption": Mock(
                return_value=envelope({"Status": "Enabled", "SSEAlgorithm": "AES256"})
            ),
            "ceph_rgw_bucket.delete_encryption": Mock(),
        },
    )
    result = state.encryption_absent("data")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]


def test_lifecycle_compares_json_semantically(monkeypatch):
    get = Mock(return_value=envelope('{"Rules":[{"Status":"Enabled","ID":"expire"}]}'))
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_bucket.get_lifecycle": get, "ceph_rgw_bucket.set_lifecycle": set_},
    )
    result = state.lifecycle_present("data", {"Rules": [{"ID": "expire", "Status": "Enabled"}]})
    assert result["result"] is True
    set_.assert_not_called()


def test_lifecycle_absent_requires_confirmation(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_bucket.get_lifecycle": Mock(return_value=envelope({"Rules": [{}]})),
            "ceph_rgw_bucket.set_lifecycle": Mock(),
        },
    )
    result = state.lifecycle_absent("data")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]


def test_notifications_update_uses_canonical_json_and_verifies(monkeypatch):
    before = {"TopicConfigurations": []}
    after = {"TopicConfigurations": [{"Id": "events"}]}
    get = Mock(side_effect=[envelope(before), envelope(after)])
    set_ = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_rgw_bucket.get_notifications": get, "ceph_rgw_bucket.set_notifications": set_},
    )
    result = state.notifications_present("data", after)
    assert result["result"] is True
    assert set_.call_args.args[1] == '{"TopicConfigurations":[{"Id":"events"}]}'


def test_notifications_absent_deletes_each_readable_id(monkeypatch):
    before = {
        "TopicConfigurations": [{"Id": "events"}],
        "QueueConfigurations": [{"Id": "queue"}],
    }
    get = Mock(side_effect=[envelope(before), envelope({})])
    delete = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_bucket.get_notifications": get,
            "ceph_rgw_bucket.delete_notification": delete,
        },
    )
    result = state.notifications_absent("data", confirm=True)
    assert result["result"] is True
    assert [call.args[1] for call in delete.call_args_list] == ["events", "queue"]


def test_notifications_absent_refuses_unknown_nonempty_shape(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_bucket.get_notifications": Mock(
                return_value=envelope({"UnknownConfigurations": [{"Id": "unsafe"}]})
            )
        },
    )
    result = state.notifications_absent("data", confirm=True)
    assert result["result"] is False
    assert "unsupported" in result["comment"]


def test_policy_updates_through_bucket_and_post_reads(monkeypatch):
    desired = {"Statement": [{"Effect": "Allow"}]}
    before = bucket(bucket_policy={})
    after = bucket(bucket_policy=desired)
    salt = bucket_reads(details=before)
    salt["ceph_rgw_bucket.list_buckets"].side_effect = [
        envelope(["data"]),
        envelope(["data"]),
    ]
    salt["ceph_rgw_bucket.get_bucket"].side_effect = [envelope(before), envelope(after)]
    salt["ceph_rgw_bucket.update_bucket"] = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.policy_present("data", desired)
    assert result["result"] is True
    assert (
        '"Effect":"Allow"'
        in salt["ceph_rgw_bucket.update_bucket"].call_args.kwargs["bucket_policy"]
    )


def test_replication_disable_requires_confirmation(monkeypatch):
    current = bucket(
        replication={
            "sync_policy_active": True,
            "replication_rules_configured": False,
        }
    )
    salt = bucket_reads(details=current)
    salt["ceph_rgw_bucket.update_bucket"] = Mock()
    monkeypatch.setattr(state, "__salt__", salt)
    result = state.replication_present("data", enabled=False)
    assert result["result"] is False
    assert "confirm_disable" in result["comment"]


def test_bucket_rate_limit_is_idempotent(monkeypatch):
    value = {
        "bucket_ratelimit": {
            "enabled": True,
            "max_read_ops": 1,
            "max_write_ops": 2,
            "max_read_bytes": 3,
            "max_write_bytes": 4,
        }
    }
    set_ = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_rgw_bucket.get_rate_limit": Mock(return_value=envelope(value)),
            "ceph_rgw_bucket.set_rate_limit": set_,
        },
    )
    result = state.rate_limit_present("data.123", True, 1, 2, 3, 4)
    assert result["result"] is True
    set_.assert_not_called()
