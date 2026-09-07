"""NFS Dashboard controller operations and validation."""

import inspect
from copy import deepcopy
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_nfs as execution
from saltext.ceph.utils.ceph import nfs
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_nfs as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(202, {"name": "nfs/create"})
    return client


@pytest.fixture
def cephfs_export():
    return {
        "path": "/volumes/team/data",
        "cluster_id": "nfs1",
        "pseudo": "/team/data",
        "access_type": "rw",
        "squash": "ROOT_SQUASH",
        "security_label": True,
        "protocols": [4],
        "transports": ["tcp"],
        "fsal": {
            "name": "ceph",
            "fs_name": "cephfs",
            "sec_label_xattr": "security.selinux",
        },
        "clients": [
            {
                "addresses": ["192.0.2.0/24", "client.example.com"],
                "access_type": "ro",
                "squash": "no_root_squash",
            }
        ],
    }


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


def test_clusters_uses_experimental_version_without_main_only_query_by_default(client):
    client.request.return_value = APIResponse(200, ["nfs1", "nfs2"])
    result = nfs.clusters(client)
    assert result.data == ["nfs1", "nfs2"]
    client.request.assert_called_once_with("GET", "/api/nfs-ganesha/cluster", api_version="0.1")


def test_clusters_info_uses_current_controller_query_and_mapping_shape(client):
    client.request.return_value = APIResponse(
        200, [{"name": "nfs1", "backend": [{"hostname": "node1"}]}]
    )
    result = nfs.clusters(client, info=True)
    assert result.data[0]["name"] == "nfs1"
    client.request.assert_called_once_with(
        "GET",
        "/api/nfs-ganesha/cluster",
        api_version="0.1",
        params={"info": True},
    )


@pytest.mark.parametrize(
    "info,payload",
    [
        (False, None),
        (False, {}),
        (False, ["nfs1", None]),
        (False, [""]),
        (True, ["nfs1"]),
        (True, [{"name": "nfs1"}, None]),
    ],
)
def test_clusters_rejects_invalid_response_shapes(client, info, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        nfs.clusters(client, info=info)


@pytest.mark.parametrize("info", [None, 0, 1, "true"])
def test_clusters_rejects_non_boolean_info_before_http(client, info):
    with pytest.raises(ConfigurationError):
        nfs.clusters(client, info=info)
    client.request.assert_not_called()


def test_list_exports_uses_v1_and_no_pagination_or_filter_by_default(client):
    client.request.return_value = APIResponse(200, [{"export_id": 1}])
    assert nfs.list_exports(client).data == [{"export_id": 1}]
    client.request.assert_called_once_with("GET", "/api/nfs-ganesha/export", api_version="1.0")


def test_list_exports_passes_current_main_cluster_filter_only_when_requested(client):
    client.request.return_value = APIResponse(200, [])
    nfs.list_exports(client, "nfs1")
    client.request.assert_called_once_with(
        "GET",
        "/api/nfs-ganesha/export",
        api_version="1.0",
        params={"cluster_id": "nfs1"},
    )


@pytest.mark.parametrize("payload", [None, {}, ["export"], [{}, None]])
def test_list_exports_rejects_non_mapping_lists(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        nfs.list_exports(client)


def test_get_export_uses_v1_and_accepts_controller_null_result(client):
    client.request.return_value = APIResponse(200, None)
    result = nfs.get_export(client, "nfs1", "7")
    assert result.data is None
    client.request.assert_called_once_with(
        "GET", "/api/nfs-ganesha/export/nfs1/7", api_version="1.0"
    )


def test_get_export_returns_detached_mapping(client):
    payload = {"export_id": 7, "cluster_id": "nfs1"}
    client.request.return_value = APIResponse(200, payload)
    result = nfs.get_export(client, "nfs1", 7)
    assert result.data == payload
    assert result.data is not payload


def test_get_export_rejects_non_mapping_non_null_response(client):
    client.request.return_value = APIResponse(200, [])
    with pytest.raises(ProtocolError):
        nfs.get_export(client, "nfs1", 1)


def test_create_cephfs_export_uses_v2_and_normalizes_structures(client, cephfs_export):
    original = deepcopy(cephfs_export)
    result = nfs.create_export(client, **cephfs_export)
    assert result.status == 202
    client.request.assert_called_once_with(
        "POST",
        "/api/nfs-ganesha/export",
        api_version="2.0",
        data={
            "path": "/volumes/team/data",
            "cluster_id": "nfs1",
            "pseudo": "/team/data",
            "access_type": "RW",
            "squash": "root_squash",
            "security_label": True,
            "protocols": [4],
            "transports": ["TCP"],
            "fsal": {
                "name": "CEPH",
                "fs_name": "cephfs",
                "sec_label_xattr": "security.selinux",
            },
            "clients": [
                {
                    "addresses": ["192.0.2.0/24", "client.example.com"],
                    "access_type": "RO",
                    "squash": "no_root_squash",
                }
            ],
        },
    )
    assert cephfs_export == original


def test_create_accepts_rgw_bucket_export(client):
    nfs.create_export(
        client,
        "bucket-one",
        "nfs1",
        "/buckets/one",
        "RO",
        "none",
        False,
        [3, 4],
        ["UDP", "TCP"],
        {"name": "RGW"},
        [],
    )
    assert client.request.call_args.kwargs["data"]["fsal"] == {"name": "RGW"}


def test_create_accepts_rgw_user_export_with_hidden_openapi_user_id(client):
    nfs.create_export(
        client,
        "/",
        "nfs1",
        "/users/alice",
        "RO",
        "root_squash",
        False,
        [4],
        ["TCP"],
        {"name": "RGW", "user_id": "tenant$alice"},
        [],
    )
    assert client.request.call_args.kwargs["data"]["fsal"] == {
        "name": "RGW",
        "user_id": "tenant$alice",
    }


def test_create_accepts_main_only_rdma_transport(client):
    nfs.create_export(
        client,
        "/",
        "nfs1",
        "/cephfs",
        "RW",
        "none",
        False,
        [4],
        ["rdma"],
        {"name": "CEPH", "fs_name": "cephfs"},
        [],
    )
    assert client.request.call_args.kwargs["data"]["transports"] == ["RDMA"]


def test_update_uses_v2_path_identity_and_excludes_route_fields_from_body(client, cephfs_export):
    cluster_id = cephfs_export.pop("cluster_id")
    nfs.update_export(client, cluster_id, 9, **cephfs_export)
    call = client.request.call_args
    assert call.args == ("PUT", "/api/nfs-ganesha/export/nfs1/9")
    assert call.kwargs["api_version"] == "2.0"
    assert "cluster_id" not in call.kwargs["data"]
    assert "export_id" not in call.kwargs["data"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("path", "relative/path"),
        ("path", "/path/../other"),
        ("pseudo", "relative"),
        ("pseudo", "/"),
        ("pseudo", "/path/../other"),
        ("pseudo", "/bad&path"),
        ("access_type", "write"),
        ("squash", "invalid"),
        ("security_label", "false"),
        ("protocols", []),
        ("protocols", [4, 4]),
        ("protocols", [2]),
        ("protocols", [True]),
        ("transports", []),
        ("transports", ["TCP", "tcp"]),
        ("transports", ["SCTP"]),
        ("fsal", []),
        ("fsal", {"name": "GLUSTER"}),
        ("fsal", {"name": "CEPH"}),
        ("fsal", {"name": "CEPH", "fs_name": "bad/name"}),
        ("fsal", {"name": "CEPH", "fs_name": "cephfs", "user_id": "custom"}),
        ("fsal", {"name": "CEPH", "fs_name": "cephfs", "secret": "value"}),
        ("clients", "192.0.2.1"),
        ("clients", [{"addresses": ["192.0.2.1"], "access_type": "RW"}]),
        (
            "clients",
            [
                {
                    "addresses": [],
                    "access_type": "RW",
                    "squash": "none",
                }
            ],
        ),
        (
            "clients",
            [
                {
                    "addresses": ["192.0.2.1", "192.0.2.1"],
                    "access_type": "RW",
                    "squash": "none",
                }
            ],
        ),
    ],
)
def test_create_rejects_invalid_cephfs_payload_before_http(client, cephfs_export, field, value):
    cephfs_export[field] = value
    with pytest.raises(ConfigurationError):
        nfs.create_export(client, **cephfs_export)
    client.request.assert_not_called()


def test_security_label_requires_cephfs_xattr(client, cephfs_export):
    cephfs_export["fsal"].pop("sec_label_xattr")
    with pytest.raises(ConfigurationError):
        nfs.create_export(client, **cephfs_export)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "path,fsal",
    [
        ("nested/bucket", {"name": "RGW"}),
        ("/", {"name": "RGW"}),
        ("bucket", {"name": "RGW", "fs_name": "cephfs"}),
        ("bucket", {"name": "RGW", "sec_label_xattr": "security.selinux"}),
        ("bucket", {"name": "RGW", "user_id": "bad user"}),
    ],
)
def test_create_rejects_invalid_rgw_fsal_combinations(client, path, fsal):
    with pytest.raises(ConfigurationError):
        nfs.create_export(
            client,
            path,
            "nfs1",
            "/rgw",
            "RO",
            "none",
            False,
            [4],
            ["TCP"],
            fsal,
            [],
        )
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "operation,args",
    [
        (nfs.list_exports, ("bad/name",)),
        (nfs.get_export, ("bad/name", 1)),
        (nfs.get_export, ("nfs1", 0)),
        (nfs.get_export, ("nfs1", True)),
    ],
)
def test_resource_identifiers_are_validated_before_http(client, operation, args):
    with pytest.raises(ConfigurationError):
        operation(client, *args)
    client.request.assert_not_called()


def test_delete_requires_confirmation_before_http(client):
    with pytest.raises(ConfigurationError):
        nfs.delete_export(client, "nfs1", 1)
    client.request.assert_not_called()


@pytest.mark.parametrize("confirm", [None, 1, "true"])
def test_delete_requires_a_boolean_confirmation(client, confirm):
    with pytest.raises(ConfigurationError):
        nfs.delete_export(client, "nfs1", 1, confirm=confirm)
    client.request.assert_not_called()


def test_delete_uses_v2_and_preserves_202_task_envelope(client):
    client.request.return_value = APIResponse(
        202, {"name": "nfs/delete", "metadata": {"export_id": 1}}
    )
    result = nfs.delete_export(client, "nfs1", 1, confirm=True)
    assert result.status == 202
    assert result.data["name"] == "nfs/delete"
    client.request.assert_called_once_with(
        "DELETE", "/api/nfs-ganesha/export/nfs1/1", api_version="2.0"
    )
