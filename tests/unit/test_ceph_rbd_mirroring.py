"""RBD mirroring controller contracts and secret handling."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_rbd_mirroring as execution
from saltext.ceph.utils.ceph import rbd_mirroring
from saltext.ceph.utils.ceph import rbd_mirroring_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_rbd_mirroring as wrapper

PEER_UUID = "2d9af31c-4268-4a38-86a5-5d45170e6ab2"


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(202, {"name": "rbd/mirroring/task"})
    return client


def test_wrapper_exports_execution_functions_with_matching_signatures():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    assert names == {
        name
        for name, function in inspect.getmembers(wrapper, inspect.isfunction)
        if not name.startswith("_")
    }
    for name in names:
        assert inspect.signature(getattr(wrapper, name)) == inspect.signature(
            getattr(execution, name)
        )


def test_summary_uses_public_route_and_redacts_nested_secrets(client):
    client.request.return_value = APIResponse(
        200,
        {
            "site_name": "site-a",
            "content_data": {"pools": [{"name": "rbd", "key": "private"}]},
        },
    )
    result = rbd_mirroring.summary(client)
    assert "private" not in repr(result.as_dict())
    assert "key" not in result.data["content_data"]["pools"][0]
    client.request.assert_called_once_with("GET", "/api/block/mirroring/summary", api_version="1.0")


def test_main_image_summary_encodes_segments(client):
    client.request.return_value = APIResponse(200, {"state": "replaying"})
    rbd_mirroring.image_summary(client, "rbd", "vm-1")
    client.request.assert_called_once_with(
        "GET", "/api/block/mirroring/rbd/vm-1/summary", api_version="1.0"
    )


def test_site_name_get_and_set_validate_shapes(client):
    client.request.return_value = APIResponse(200, {"site_name": "site-a"})
    assert rbd_mirroring.get_site_name(client).data == {"site_name": "site-a"}
    client.reset_mock()
    rbd_mirroring.set_site_name(client, "Moscow primary")
    client.request.assert_called_once_with(
        "PUT",
        "/api/block/mirroring/site_name",
        api_version="1.0",
        data={"site_name": "Moscow primary"},
    )
    client.request.return_value = APIResponse(200, {})
    with pytest.raises(ProtocolError):
        rbd_mirroring.get_site_name(client)


def test_pool_mode_get_and_main_init_only_update(client):
    client.request.return_value = APIResponse(200, {"mirror_mode": "image"})
    assert rbd_mirroring.get_pool_mode(client, "rbd").data["mirror_mode"] == "image"
    client.reset_mock()
    rbd_mirroring.set_pool_mode(client, "rbd", "init-only")
    client.request.assert_called_once_with(
        "PUT",
        "/api/block/mirroring/pool/rbd",
        api_version="1.0",
        data={"mirror_mode": "init-only"},
    )


@pytest.mark.parametrize("confirm", [False, "true", 1])
def test_disabling_pool_mirroring_requires_exact_confirmation(client, confirm):
    with pytest.raises(ConfigurationError):
        rbd_mirroring.set_pool_mode(client, "rbd", "disabled", confirm=confirm)
    client.request.assert_not_called()


def test_disabling_pool_mirroring_succeeds_when_confirmed(client):
    rbd_mirroring.set_pool_mode(client, "rbd", "disabled", confirm=True)
    assert client.request.call_args.kwargs["data"] == {"mirror_mode": "disabled"}


def test_bootstrap_token_raw_contract_requires_single_secret(client):
    client.request.return_value = APIResponse(201, {"token": "cHJpdmF0ZQ=="})
    response = rbd_mirroring.create_bootstrap_token(client, "rbd")
    assert response.data == {"token": "cHJpdmF0ZQ=="}
    client.request.assert_called_once_with(
        "POST",
        "/api/block/mirroring/pool/rbd/bootstrap/token",
        api_version="1.0",
        data={},
    )
    client.request.return_value = APIResponse(201, {})
    with pytest.raises(ProtocolError):
        rbd_mirroring.create_bootstrap_token(client, "rbd")


def test_api_writes_bootstrap_token_without_returning_it(tmp_path, monkeypatch):
    destination = tmp_path / "bootstrap.token"
    client = Mock()
    client.request.return_value = APIResponse(201, {"token": "cHJpdmF0ZQ=="})
    monkeypatch.setattr(rbd_mirroring_api, "_client", lambda *_args: client)
    result = rbd_mirroring_api.create_bootstrap_token({}, {}, {}, "rbd", str(destination))
    assert destination.read_text(encoding="utf-8") == "cHJpdmF0ZQ=="
    assert result["data"] == {"pool_name": "rbd", "destination": str(destination)}
    assert "cHJpdmF0ZQ==" not in repr(result)


def test_api_rejects_relative_token_destination_before_getting_client(monkeypatch):
    get_client = Mock()
    monkeypatch.setattr(rbd_mirroring_api, "_client", get_client)
    with pytest.raises(ConfigurationError, match="absolute"):
        rbd_mirroring_api.create_bootstrap_token({}, {}, {}, "rbd", "token")
    get_client.assert_not_called()


def test_api_imports_newline_terminated_token_without_echo(tmp_path, monkeypatch):
    source = tmp_path / "bootstrap.token"
    source.write_text("cHJpdmF0ZQ==\r\n", encoding="utf-8")
    client = Mock()
    client.request.return_value = APIResponse(201, {"token": "unexpected-echo"})
    monkeypatch.setattr(rbd_mirroring_api, "_client", lambda *_args: client)
    result = rbd_mirroring_api.import_bootstrap_token(
        {}, {}, {}, "rbd", str(source), direction="rx"
    )
    assert result["data"] == {"pool_name": "rbd"}
    assert "cHJpdmF0ZQ" not in repr(result)
    assert "unexpected-echo" not in repr(result)
    assert client.request.call_args.kwargs["data"] == {
        "direction": "rx",
        "token": "cHJpdmF0ZQ==",
    }


def test_api_rejects_relative_token_source_before_getting_client(monkeypatch):
    get_client = Mock()
    monkeypatch.setattr(rbd_mirroring_api, "_client", get_client)
    with pytest.raises(ConfigurationError, match="absolute"):
        rbd_mirroring_api.import_bootstrap_token({}, {}, {}, "rbd", "token")
    get_client.assert_not_called()


@pytest.mark.parametrize("direction", ["rx-only", "tx", "", None])
def test_bootstrap_import_rejects_dashboard_unsupported_directions(client, direction):
    with pytest.raises(ConfigurationError):
        rbd_mirroring.import_bootstrap_token(client, "rbd", direction, "token")
    client.request.assert_not_called()


def test_peer_list_and_get_follow_controller_shapes_and_redact_key(client):
    client.request.return_value = APIResponse(200, [PEER_UUID])
    assert rbd_mirroring.list_peers(client, "rbd").data == [PEER_UUID]
    client.reset_mock()
    client.request.return_value = APIResponse(
        200,
        {
            "uuid": PEER_UUID,
            "cluster_name": "remote",
            "client_id": "mirror",
            "key": "AQ-private==",
        },
    )
    result = rbd_mirroring.get_peer(client, "rbd", PEER_UUID)
    assert result.data == {
        "uuid": PEER_UUID,
        "cluster_name": "remote",
        "client_id": "mirror",
    }
    assert "AQ-private" not in repr(result)


def test_create_peer_api_reads_key_file_and_does_not_return_key(tmp_path, monkeypatch):
    source = tmp_path / "peer.key"
    source.write_text("AQ-private==\n", encoding="utf-8")
    client = Mock()
    client.request.return_value = APIResponse(201, {"uuid": PEER_UUID, "key": "AQ-private=="})
    monkeypatch.setattr(rbd_mirroring_api, "_client", lambda *_args: client)
    result = rbd_mirroring_api.create_peer(
        {},
        {},
        {},
        "rbd",
        "remote",
        "mirror",
        mon_host="v2:192.0.2.10:3300",
        key_source=str(source),
    )
    assert result["data"] == {"uuid": PEER_UUID}
    assert "AQ-private" not in repr(result)
    assert client.request.call_args.kwargs["data"]["key"] == "AQ-private=="


def test_update_peer_can_clear_key_without_exposing_it(client):
    client.request.return_value = APIResponse(200, {"key": "unexpected"})
    result = rbd_mirroring.update_peer(client, "rbd", PEER_UUID, key="")
    assert "unexpected" not in repr(result.as_dict())
    assert client.request.call_args.kwargs["data"] == {"key": ""}


def test_api_update_peer_rejects_two_key_sources_before_client(monkeypatch):
    get_client = Mock()
    monkeypatch.setattr(rbd_mirroring_api, "_client", get_client)
    with pytest.raises(ConfigurationError, match="mutually exclusive"):
        rbd_mirroring_api.update_peer(
            {}, {}, {}, "rbd", PEER_UUID, key_source="C:\\key", clear_key=True
        )
    get_client.assert_not_called()


@pytest.mark.parametrize(
    "function,args",
    [
        (rbd_mirroring.get_peer, ("rbd", "not-a-uuid")),
        (rbd_mirroring.create_peer, ("rbd", "bad cluster", "mirror")),
        (rbd_mirroring.update_peer, ("rbd", PEER_UUID)),
        (rbd_mirroring.set_site_name, ("bad\nsite",)),
        (rbd_mirroring.set_pool_mode, ("rbd", "namespace")),
    ],
)
def test_invalid_peer_and_site_inputs_fail_before_http(client, function, args):
    with pytest.raises(ConfigurationError):
        function(client, *args)
    client.request.assert_not_called()


def test_peer_delete_requires_confirmation_and_uses_member_route(client):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        rbd_mirroring.delete_peer(client, "rbd", PEER_UUID)
    client.request.assert_not_called()
    rbd_mirroring.delete_peer(client, "rbd", PEER_UUID, confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        f"/api/block/mirroring/pool/rbd/peer/{PEER_UUID}",
        api_version="1.0",
    )


def test_api_rejects_unknown_operation():
    with pytest.raises(ConfigurationError, match="Unknown RBD mirroring operation"):
        rbd_mirroring_api.call({}, {}, {}, "missing")
