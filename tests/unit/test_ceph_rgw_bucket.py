"""RGW bucket Dashboard adapter tests across Reef and current Ceph."""

import inspect
from copy import deepcopy
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rgw_bucket as execution
from saltext.ceph.utils.ceph import rgw_bucket
from saltext.ceph.utils.ceph import rgw_bucket_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rgw_bucket as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, {})
    return client


def test_wrapper_matches_execution_module():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    for name in names:
        assert inspect.signature(getattr(execution, name)) == inspect.signature(
            getattr(wrapper, name)
        )
        api_parameters = list(inspect.signature(getattr(rgw_bucket_api, name)).parameters.values())
        assert inspect.signature(getattr(execution, name)) == inspect.Signature(api_parameters[3:])


def test_list_buckets_always_uses_controller_v1_1(client):
    client.request.return_value = APIResponse(200, ["tenant/bucket"])
    rgw_bucket.list_buckets(client, daemon_name="rgw.a", uid="tenant$alice")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/bucket",
        api_version="1.1",
        params={"stats": False, "daemon_name": "rgw.a", "uid": "tenant$alice"},
    )


def test_list_buckets_with_stats_requires_mapping_items(client):
    client.request.return_value = APIResponse(200, [{"bucket": "data"}])
    assert rgw_bucket.list_buckets(client, stats=True).data == [{"bucket": "data"}]
    client.request.return_value = APIResponse(200, ["data"])
    with pytest.raises(ProtocolError):
        rgw_bucket.list_buckets(client, stats=True)


@pytest.mark.parametrize("payload", [None, {}, [None], [1], [{"bucket": "data"}]])
def test_list_buckets_rejects_invalid_shapes(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        rgw_bucket.list_buckets(client)


def test_get_bucket_encodes_tenant_path(client):
    client.request.return_value = APIResponse(200, {"bucket": "data"})
    rgw_bucket.get_bucket(client, "tenant/data", "rgw.a")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/bucket/tenant%2Fdata",
        api_version="1.0",
        params={"daemon_name": "rgw.a"},
    )


def test_create_bucket_omits_current_replication_for_reef_by_default(client):
    rgw_bucket.create_bucket(client, "data", "alice")
    data = client.request.call_args.kwargs["data"]
    assert client.request.call_args.args == ("POST", "/api/rgw/bucket")
    assert client.request.call_args.kwargs["api_version"] == "1.0"
    assert data == {
        "bucket": "data",
        "uid": "alice",
        "lock_enabled": False,
        "encryption_state": False,
    }


def test_bucket_api_preserves_safe_create_defaults_across_layers(client, monkeypatch):
    monkeypatch.setattr(rgw_bucket_api.ceph, "get_client", lambda *_: client)

    rgw_bucket_api.create_bucket({}, {}, {}, "data", "alice")

    assert client.request.call_args.kwargs["data"] == {
        "bucket": "data",
        "uid": "alice",
        "lock_enabled": False,
        "encryption_state": False,
    }


def test_create_bucket_sends_structured_current_options_without_mutation(client):
    kwargs = {
        "zonegroup": "zg1",
        "placement_target": "default-placement",
        "lock_enabled": True,
        "lock_mode": "COMPLIANCE",
        "lock_retention_period_days": "30",
        "encryption_state": True,
        "encryption_type": "kms",
        "key_id": "archive-key",
        "tags": '[{"Key":"team","Value":"ops"}]',
        "bucket_policy": '{"Statement":[]}',
        "canned_acl": "private",
        "replication": True,
        "daemon_name": "rgw.a",
    }
    original = deepcopy(kwargs)
    rgw_bucket.create_bucket(client, "data", "alice", **kwargs)
    assert kwargs == original
    assert client.request.call_args.kwargs["data"]["replication"] is True
    assert client.request.call_args.kwargs["data"]["lock_retention_period_days"] == 30


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lock_enabled": "true"},
        {"lock_enabled": True},
        {"lock_enabled": True, "lock_mode": "LEGAL"},
        {"encryption_state": "false"},
        {"encryption_state": True},
        {"encryption_state": True, "encryption_type": "AES256"},
        {"replication": "true"},
        {"lock_retention_period_days": -1},
        {"lock_retention_period_days": 30, "lock_retention_period_years": 1},
    ],
)
def test_create_bucket_rejects_unsafe_values_before_http(client, kwargs):
    with pytest.raises(ConfigurationError):
        rgw_bucket.create_bucket(client, "data", "alice", **kwargs)
    client.request.assert_not_called()


def test_update_bucket_omits_main_only_fields_for_reef_by_default(client):
    client.request.side_effect = [
        APIResponse(200, {"bucket": "data", "encryption": "Disabled"}),
        APIResponse(200, {}),
    ]
    rgw_bucket.update_bucket(client, "data", "bucket.123", uid="alice")
    assert client.request.call_args_list[-1].args == ("PUT", "/api/rgw/bucket/data")
    data = client.request.call_args_list[-1].kwargs["data"]
    assert data == {
        "bucket_id": "bucket.123",
        "uid": "alice",
        "encryption_state": False,
    }
    assert "replication" not in data
    assert "lifecycle" not in data


def test_update_bucket_accepts_current_replication_and_lifecycle(client):
    rgw_bucket.update_bucket(
        client,
        "data",
        "id",
        uid="alice",
        encryption_state=False,
        versioning_state="Enabled",
        replication=False,
        lifecycle='{"Rules":[]}',
        confirm_encryption_disable=True,
        confirm_replication_disable=True,
    )
    data = client.request.call_args.kwargs["data"]
    assert data["replication"] is False
    assert data["lifecycle"] == '{"Rules":[]}'


def test_update_bucket_reads_before_write_to_preserve_current_sensitive_features(client):
    client.request.side_effect = [
        APIResponse(
            200,
            {
                "bucket": "data",
                "owner": "alice",
                "encryption": "Enabled",
                "lifecycle": {"Rules": [{"ID": "archive"}]},
                "replication": False,
            },
        ),
        APIResponse(200, None),
    ]
    rgw_bucket.update_bucket(client, "data", "id")
    assert client.request.call_count == 2
    data = client.request.call_args_list[-1].kwargs["data"]
    assert data["encryption_state"] is True
    assert data["lifecycle"] == '{"Rules":[{"ID":"archive"}]}'
    assert data["uid"] == "alice"


def test_update_bucket_preserves_empty_lifecycle_without_delete_confirmation(client):
    client.request.side_effect = [
        APIResponse(
            200,
            {
                "bucket": "data",
                "owner": "alice",
                "encryption": "Disabled",
                "lifecycle": {},
                "replication": False,
            },
        ),
        APIResponse(200, None),
    ]

    rgw_bucket.update_bucket(client, "data", "id")

    assert client.request.call_args_list[-1].kwargs["data"]["lifecycle"] == "{}"


@pytest.mark.parametrize(
    "payload",
    [
        {"encryption": "Disabled"},
        {"owner": "alice", "encryption": "Unknown"},
        {"owner": "alice", "encryption": "Disabled", "lifecycle": []},
        {"owner": "alice", "encryption": "Disabled", "replication": False},
    ],
)
def test_update_bucket_refuses_to_guess_omitted_current_values(client, payload):
    client.request.return_value = APIResponse(200, payload)

    with pytest.raises(ProtocolError):
        rgw_bucket.update_bucket(client, "data", "id")

    client.request.assert_called_once_with(
        "GET", "/api/rgw/bucket/data", api_version="1.0", params={}
    )


def test_update_bucket_destructive_and_ambiguous_values_fail_before_write(client):
    with pytest.raises(ConfigurationError):
        rgw_bucket.update_bucket(
            client,
            "data",
            "id",
            uid="alice",
            encryption_state=True,
            lifecycle="{}",
        )
    client.request.assert_not_called()

    with pytest.raises(ConfigurationError):
        rgw_bucket.update_bucket(
            client,
            "data",
            "id",
            uid="alice",
            encryption_state=True,
            lifecycle='{"Rules":[]}',
            lock_retention_period_days=30,
            lock_retention_period_years=1,
        )
    client.request.assert_not_called()


def test_update_bucket_requires_confirmation_to_disable_replication(client):
    with pytest.raises(ConfigurationError):
        rgw_bucket.update_bucket(
            client,
            "data",
            "id",
            uid="alice",
            encryption_state=True,
            lifecycle='{"Rules":[]}',
            replication=False,
        )
    client.request.assert_not_called()


@pytest.mark.parametrize("confirm", [False, None, "true", 1])
def test_delete_bucket_requires_literal_true(client, confirm):
    with pytest.raises(ConfigurationError):
        rgw_bucket.delete_bucket(client, "data", confirm=confirm)
    client.request.assert_not_called()


def test_delete_bucket_preserves_204(client):
    client.request.return_value = APIResponse(204, None)
    result = rgw_bucket.delete_bucket(client, "tenant/data", confirm=True)
    assert result.status == 204
    client.request.assert_called_once_with(
        "DELETE", "/api/rgw/bucket/tenant%2Fdata", api_version="1.0", params={}
    )


def test_current_vault_encryption_config_is_nested_and_detached(client):
    config = {
        "addr": "https://vault:8200",
        "auth": "agent",
        "prefix": "/v1/secret/data",
        "secret_engine": "kv",
        "verify_ssl": True,
        "token_file": "/run/secrets/vault-token",
    }
    original = deepcopy(config)
    rgw_bucket.set_encryption_config(client, "kms", "vault", config, "rgw.a")
    assert config == original
    client.request.assert_called_once_with(
        "PUT",
        "/api/rgw/bucket/setEncryptionConfig",
        api_version="1.0",
        data={
            "encryption_type": "kms",
            "kms_provider": "vault",
            "config": config,
            "daemon_name": "rgw.a",
        },
    )
    assert client.request.call_args.kwargs["data"]["config"] is not config


def test_reef_encryption_config_is_flattened_explicitly(client):
    config = {
        "auth_method": "token",
        "secret_engine": "kv",
        "secret_path": "ceph/keys",
        "address": "https://vault:8200",
        "token": "sensitive",
    }
    rgw_bucket.set_encryption_config(client, "kms", "vault", config, "rgw.a", reef_legacy=True)
    assert "config" not in client.request.call_args.kwargs["data"]
    assert client.request.call_args.kwargs["data"]["token"] == "sensitive"


@pytest.mark.parametrize(
    "provider,config",
    [
        ("consul", {"addr": "https://x"}),
        ("vault", {"addr": "https://x"}),
        ("kmip", {"addr": "kmip:5696", "unknown": True}),
        ("vault", {"auth_method": "token", "unknown": "x"}),
    ],
)
def test_encryption_config_rejects_mismatched_structures(client, provider, config):
    with pytest.raises(ConfigurationError):
        rgw_bucket.set_encryption_config(client, "kms", provider, config, "rgw.a")
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "provider,config",
    [
        (
            "vault",
            {"addr": "", "auth": "agent", "prefix": "ceph", "secret_engine": "kv"},
        ),
        (
            "vault",
            {
                "addr": "https://vault",
                "auth": "agent",
                "prefix": "ceph",
                "secret_engine": "kv",
                "verify_ssl": "true",
            },
        ),
        ("kmip", {"addr": ["kmip:5696"]}),
    ],
)
def test_current_encryption_config_rejects_invalid_field_values(client, provider, config):
    with pytest.raises(ConfigurationError):
        rgw_bucket.set_encryption_config(client, "kms", provider, config, "rgw.a")
    client.request.assert_not_called()


def test_reef_encryption_config_rejects_non_text_values(client):
    with pytest.raises(ConfigurationError):
        rgw_bucket.set_encryption_config(
            client,
            "kms",
            "vault",
            {"address": ["https://vault"]},
            "rgw.a",
            reef_legacy=True,
        )
    client.request.assert_not_called()


def test_reef_encryption_config_rejects_unknown_fields(client):
    with pytest.raises(ConfigurationError):
        rgw_bucket.set_encryption_config(
            client,
            "kms",
            "vault",
            {"address": "https://vault", "unknown": "value"},
            "rgw.a",
            reef_legacy=True,
        )
    client.request.assert_not_called()


def test_get_encryption_config_redacts_nested_credentials(client):
    payload = {
        "kms": {
            "vault": {"addr": "https://vault", "token_file": "/run/token"},
            "kmip": {"username": "ceph", "password": "secret"},
        }
    }
    client.request.return_value = APIResponse(200, payload)
    result = rgw_bucket.get_encryption_config(client)
    assert result.data["kms"]["vault"]["token_file"] == "***********"
    assert result.data["kms"]["kmip"]["password"] == "***********"
    assert result.data["redacted"] is True


def test_encryption_config_secret_opt_in_is_explicit(client):
    payload = {"token": "secret"}
    client.request.return_value = APIResponse(200, payload)
    result = rgw_bucket.get_encryption_config(client, include_secrets=True)
    assert result.data == payload
    assert result.data is not payload


def test_encryption_config_rejects_non_boolean_secret_opt_in_before_request(client):
    with pytest.raises(ConfigurationError):
        rgw_bucket.get_encryption_config(client, include_secrets="true")
    client.request.assert_not_called()


def test_encryption_read_and_guarded_delete_use_collection_queries(client):
    client.request.return_value = APIResponse(200, {"Status": "Enabled"})
    rgw_bucket.get_encryption(client, "tenant:data", owner="alice")
    client.request.assert_called_once_with(
        "GET",
        "/api/rgw/bucket/getEncryption",
        api_version="1.0",
        params={"bucket_name": "tenant:data", "owner": "alice"},
    )
    client.reset_mock()
    with pytest.raises(ConfigurationError):
        rgw_bucket.delete_encryption(client, "tenant:data")
    client.request.assert_not_called()

    client.request.return_value = APIResponse(204, None)
    rgw_bucket.delete_encryption(client, "tenant:data", owner="alice", confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        "/api/rgw/bucket/deleteEncryption",
        api_version="1.0",
        params={"bucket_name": "tenant:data", "owner": "alice"},
    )


def test_current_lifecycle_and_notification_routes(client):
    rgw_bucket.set_lifecycle(client, "data", '{"Rules":[]}', owner="alice", tenant="t")
    assert client.request.call_args.args == ("PUT", "/api/rgw/bucket/lifecycle")
    assert client.request.call_args.kwargs["data"]["tenant"] == "t"
    client.reset_mock()
    rgw_bucket.get_lifecycle(client, "data", owner="alice", tenant="t")
    assert client.request.call_args.args == ("GET", "/api/rgw/bucket/lifecycle")
    client.reset_mock()
    rgw_bucket.set_notifications(client, "data", '{"TopicConfigurations":[]}', owner="alice")
    assert client.request.call_args.args == ("PUT", "/api/rgw/bucket/notification")
    client.reset_mock()
    rgw_bucket.get_notifications(client, "data")
    assert client.request.call_args.args == ("GET", "/api/rgw/bucket/notification")


@pytest.mark.parametrize(
    "operation,args",
    [
        (rgw_bucket.set_lifecycle, ("data", None)),
        (rgw_bucket.set_notifications, ("data", None)),
    ],
)
def test_policy_setters_require_text_before_http(client, operation, args):
    with pytest.raises(ConfigurationError):
        operation(client, *args)
    client.request.assert_not_called()


@pytest.mark.parametrize("operation", ["lifecycle", "notification"])
def test_overloaded_empty_configuration_deletes_require_confirmation(client, operation):
    with pytest.raises(ConfigurationError):
        if operation == "lifecycle":
            rgw_bucket.set_lifecycle(client, "data", "{}")
        else:
            rgw_bucket.set_notifications(client, "data", "{}")
    client.request.assert_not_called()
    if operation == "lifecycle":
        rgw_bucket.set_lifecycle(client, "data", "{}", confirm_delete=True)
    else:
        rgw_bucket.set_notifications(client, "data", "{}", confirm_delete=True)
    assert client.request.call_args.args[0] == "PUT"


def test_notification_deletion_requires_confirmation_and_query_identity(client):
    with pytest.raises(ConfigurationError):
        rgw_bucket.delete_notification(client, "data", "notify-1")
    client.request.assert_not_called()
    client.request.return_value = APIResponse(204, None)
    rgw_bucket.delete_notification(client, "data", "notify-1", confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        "/api/rgw/bucket/notification",
        api_version="1.0",
        params={"bucket_name": "data", "notification_id": "notify-1"},
    )


def test_current_rate_limit_routes_and_exact_numeric_body(client):
    client.request.return_value = APIResponse(200, {})
    rgw_bucket.get_global_rate_limit(client)
    client.request.assert_called_once_with("GET", "/api/rgw/bucket/ratelimit", api_version="1.0")
    client.reset_mock()
    rgw_bucket.get_rate_limit(client, "tenant/data")
    client.request.assert_called_once_with(
        "GET", "/api/rgw/bucket/tenant%2Fdata/ratelimit", api_version="1.0"
    )
    client.reset_mock()
    rgw_bucket.set_rate_limit(client, "data", True, "10", 20, 30, 40)
    client.request.assert_called_once_with(
        "PUT",
        "/api/rgw/bucket/data/ratelimit",
        api_version="1.0",
        data={
            "enabled": True,
            "max_read_ops": 10,
            "max_write_ops": 20,
            "max_read_bytes": 30,
            "max_write_bytes": 40,
        },
    )


@pytest.mark.parametrize("value", [-1, True, "1.5"])
def test_rate_limit_rejects_invalid_numbers(client, value):
    with pytest.raises(ConfigurationError):
        rgw_bucket.set_rate_limit(client, "data", True, value, 0, 0, 0)
    client.request.assert_not_called()


def test_update_bucket_requires_confirmation_to_disable_encryption(client):
    with pytest.raises(ConfigurationError):
        rgw_bucket.update_bucket(
            client,
            "data",
            "id",
            encryption_state=False,
            lifecycle='{"Rules":[]}',
        )
    client.request.assert_not_called()


def test_bucket_api_reads_mfa_pin_from_absolute_secret_file(client, monkeypatch, tmp_path):
    pin_source = tmp_path / "mfa-pin"
    pin_source.write_text("123456\n", encoding="utf-8")
    monkeypatch.setattr(rgw_bucket_api.ceph, "get_client", lambda *_: client)

    rgw_bucket_api.update_bucket(
        {},
        {},
        {},
        "data",
        "id",
        uid="alice",
        encryption_state=True,
        lifecycle='{"Rules":[]}',
        mfa_token_pin_source=str(pin_source),
    )

    assert client.request.call_args.kwargs["data"]["mfa_token_pin"] == "123456"
    assert "mfa_token_pin" not in inspect.signature(execution.update_bucket).parameters
    assert "mfa_token_pin_source" in inspect.signature(execution.update_bucket).parameters


def test_bucket_api_reads_secret_kms_mapping_from_json_file(client, monkeypatch, tmp_path):
    config_source = tmp_path / "kms.json"
    config_source.write_text(
        '{"addr":"https://vault:8200","auth":"token",'
        '"prefix":"ceph","secret_engine":"kv","token_file":"/run/token"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(rgw_bucket_api.ceph, "get_client", lambda *_: client)

    rgw_bucket_api.set_encryption_config({}, {}, {}, "kms", "vault", str(config_source), "rgw.a")

    assert client.request.call_args.kwargs["data"]["config"]["token_file"] == "/run/token"
    parameters = inspect.signature(execution.set_encryption_config).parameters
    assert "config" not in parameters
    assert "config_source" in parameters


def test_bucket_api_rejects_inline_or_invalid_kms_source(client, monkeypatch, tmp_path):
    invalid_source = tmp_path / "kms.json"
    invalid_source.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(rgw_bucket_api.ceph, "get_client", lambda *_: client)

    with pytest.raises(ConfigurationError):
        rgw_bucket_api.set_encryption_config(
            {}, {}, {}, "kms", "vault", str(invalid_source), "rgw.a"
        )
    client.request.assert_not_called()
