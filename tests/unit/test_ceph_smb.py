"""Current Ceph SMB controller tests."""

# pylint: disable=redefined-outer-name

import inspect
import json
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_smb as execution
from saltext.ceph.utils.ceph import smb
from saltext.ceph.utils.ceph import smb_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_smb as wrapper


@pytest.fixture
def client():
    result = Mock()
    result.request.return_value = APIResponse(200, {})
    return result


def test_wrapper_matches_execution_module():
    functions = {
        name: function
        for name, function in vars(execution).items()
        if inspect.isfunction(function)
        and function.__module__ == execution.__name__
        and not name.startswith("_")
    }
    assert functions
    for name, function in functions.items():
        assert inspect.signature(getattr(wrapper, name)) == inspect.signature(function)


@pytest.mark.parametrize(
    "function,path,payload",
    [
        (smb.list_clusters, "/api/smb/cluster", []),
        (smb.list_join_auths, "/api/smb/joinauth", []),
        (smb.list_usersgroups, "/api/smb/usersgroups", []),
    ],
)
def test_list_routes(client, function, path, payload):
    client.request.return_value = APIResponse(200, payload)
    function(client)
    client.request.assert_called_once_with("GET", path, api_version="1.0")


def test_get_routes(client):
    smb.get_cluster(client, "cluster-a")
    assert client.request.call_args.args[:2] == ("GET", "/api/smb/cluster/cluster-a")
    client.reset_mock()
    smb.get_share(client, "cluster-a", "share-a")
    assert client.request.call_args.args[:2] == (
        "GET",
        "/api/smb/share/cluster-a/share-a",
    )
    client.reset_mock()
    smb.get_join_auth(client, "join-a")
    assert client.request.call_args.args[:2] == ("GET", "/api/smb/joinauth/join-a")
    client.reset_mock()
    smb.get_usersgroups(client, "ug-a")
    assert client.request.call_args.args[:2] == ("GET", "/api/smb/usersgroups/ug-a")


def test_cluster_create_normalizes_resource(client):
    resource = {
        "cluster_id": "cluster-a",
        "auth_mode": "user",
        "user_group_settings": [{"source_type": "resource", "ref": "ug-a"}],
    }
    smb.create_cluster(client, resource)
    sent = client.request.call_args.kwargs["data"]["cluster_resource"]
    assert sent["resource_type"] == "ceph.smb.cluster"
    assert sent["intent"] == "present"
    assert resource.get("intent") is None


def test_share_list_filter_and_create(client):
    client.request.return_value = APIResponse(200, [])
    smb.list_shares(client, "cluster-a")
    client.request.assert_called_once_with(
        "GET",
        "/api/smb/share",
        api_version="1.0",
        params={"cluster_id": "cluster-a"},
    )
    client.reset_mock()
    client.request.return_value = APIResponse(201, {})
    smb.create_share(
        client,
        {
            "cluster_id": "cluster-a",
            "share_id": "share-a",
            "name": "Files",
            "cephfs": {"volume": "fs", "path": "/"},
        },
    )
    resource = client.request.call_args.kwargs["data"]["share_resource"]
    assert resource["resource_type"] == "ceph.smb.share"


def test_qos_update_sends_only_declared_limits(client):
    smb.update_share_qos(
        client,
        "cluster-a",
        "share-a",
        read_iops_limit=1000,
        write_delay_max=30,
    )
    client.request.assert_called_once_with(
        "PUT",
        "/api/smb/share/qos",
        api_version="1.0",
        data={
            "cluster_id": "cluster-a",
            "share_id": "share-a",
            "read_iops_limit": 1000,
            "write_delay_max": 30,
        },
    )


@pytest.mark.parametrize(
    "function,args,path",
    [
        (smb.delete_cluster, ("cluster-a", True), "/api/smb/cluster/cluster-a"),
        (
            smb.delete_share,
            ("cluster-a", "share-a", True),
            "/api/smb/share/cluster-a/share-a",
        ),
        (smb.delete_join_auth, ("join-a", True), "/api/smb/joinauth/join-a"),
        (smb.delete_usersgroups, ("ug-a", True), "/api/smb/usersgroups/ug-a"),
    ],
)
def test_deletes_use_current_routes(client, function, args, path):
    client.request.return_value = APIResponse(204, None)
    function(client, *args)
    client.request.assert_called_once_with("DELETE", path, api_version="1.0")


@pytest.mark.parametrize(
    "function,args",
    [
        (smb.delete_cluster, ("cluster-a",)),
        (smb.delete_share, ("cluster-a", "share-a")),
        (smb.delete_join_auth, ("join-a",)),
        (smb.delete_usersgroups, ("ug-a",)),
    ],
)
def test_deletes_require_confirmation(client, function, args):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        function(client, *args)
    client.request.assert_not_called()


def test_join_auth_return_is_recursively_redacted(client):
    client.request.return_value = APIResponse(
        201,
        {
            "resource_type": "ceph.smb.join.auth",
            "auth": {"username": "admin", "password": "private"},
        },
    )
    response = smb.create_join_auth(client, "join-a", "admin", "private")
    assert response.data["auth"]["password"] == "***********"
    assert response.data["auth"]["redacted"] is True
    assert response.data["redacted"] is True
    assert "private" not in repr(response.as_dict())
    assert client.request.call_args.kwargs["data"]["join_auth"]["auth"]["password"] == "private"


def test_usersgroups_return_list_is_redacted(client):
    client.request.return_value = APIResponse(
        200,
        [{"values": {"users": [{"name": "alice", "password": "private"}], "groups": []}}],
    )
    result = smb.list_usersgroups(client).data
    assert result[0]["values"]["users"][0]["password"] == "***********"
    assert result[0]["redacted"] is True


def test_api_reads_join_password_from_secret_file(client, monkeypatch, tmp_path):
    source = tmp_path / "password"
    source.write_text("private\n", encoding="utf-8")
    monkeypatch.setattr(smb_api.ceph, "get_client", Mock(return_value=client))
    smb_api.create_join_auth({}, {}, {}, "join-a", "admin", str(source))
    assert client.request.call_args.kwargs["data"]["join_auth"]["auth"]["password"] == "private"


def test_api_reads_usersgroups_from_secret_json(client, monkeypatch, tmp_path):
    source = tmp_path / "users.json"
    source.write_text(
        json.dumps({"users": [{"name": "alice", "password": "private"}], "groups": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(smb_api.ceph, "get_client", Mock(return_value=client))
    smb_api.create_usersgroups({}, {}, {}, "ug-a", str(source))
    sent = client.request.call_args.kwargs["data"]["usersgroups"]
    assert sent["values"]["users"][0]["password"] == "private"


@pytest.mark.parametrize(
    "function,args",
    [
        (smb.get_cluster, ("bad/id",)),
        (smb.create_cluster, ({"cluster_id": "a", "auth_mode": "invalid"},)),
        (
            smb.create_cluster,
            ({"cluster_id": "a", "auth_mode": "user", "password": "inline"},),
        ),
        (smb.create_share, ({"cluster_id": "a", "share_id": "b"},)),
        (smb.update_share_qos, ("a", "b")),
        (smb.create_join_auth, ("a", "", "password")),
        (smb.create_usersgroups, ("a", {"users": [], "groups": {}})),
    ],
)
def test_invalid_arguments_fail_before_http(client, function, args):
    with pytest.raises(ConfigurationError):
        function(client, *args)
    client.request.assert_not_called()


def test_qos_limit_maximum_is_validated_before_http(client):
    with pytest.raises(ConfigurationError, match="maximum"):
        smb.update_share_qos(client, "a", "b", read_delay_max=301)
    client.request.assert_not_called()


@pytest.mark.parametrize("payload", [None, [], "bad"])
def test_get_rejects_non_mapping_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        smb.get_cluster(client, "cluster-a")
