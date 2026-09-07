"""CephFS controller endpoint contracts and validation."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import cephfs as cephfs_module
from saltext.ceph.utils.ceph import cephfs
from saltext.ceph.utils.ceph import cephfs_api
from saltext.ceph.utils.ceph import cephfs_mirror
from saltext.ceph.utils.ceph import cephfs_schedule
from saltext.ceph.utils.ceph import cephfs_volumes
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import cephfs as cephfs_wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, {})
    return client


def test_wrapper_exports_every_execution_function_with_the_same_signature():
    functions = {
        name: function
        for name, function in vars(cephfs_module).items()
        if inspect.isfunction(function)
        and function.__module__ == cephfs_module.__name__
        and not name.startswith("_")
    }
    assert len(functions) == 60
    for name, function in functions.items():
        wrapper = getattr(cephfs_wrapper, name)
        assert inspect.signature(wrapper) == inspect.signature(function)


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (cephfs.list_, ("GET", "/api/cephfs", {})),
        (lambda c: cephfs.get(c, 3), ("GET", "/api/cephfs/3", {})),
        (
            lambda c: cephfs.evict_client(c, "3", 9, confirm=True),
            ("DELETE", "/api/cephfs/3/client/9", {}),
        ),
        (
            lambda c: cephfs.make_directory(c, 3, "/projects/a"),
            ("POST", "/api/cephfs/3/tree", {"data": {"path": "/projects/a"}}),
        ),
        (
            lambda c: cephfs.remove_directory(c, 3, "/projects/a", confirm=True),
            ("DELETE", "/api/cephfs/3/tree", {"params": {"path": "/projects/a"}}),
        ),
        (
            lambda c: cephfs.set_quota(c, 3, "/projects", max_bytes=1024, max_files=5),
            (
                "PUT",
                "/api/cephfs/3/quota",
                {"data": {"path": "/projects", "max_bytes": 1024, "max_files": 5}},
            ),
        ),
        (
            lambda c: cephfs.rename_path(c, 3, "/old", "/new", confirm=True),
            (
                "PUT",
                "/api/cephfs/3/rename-path",
                {"data": {"src_path": "/old", "dst_path": "/new"}},
            ),
        ),
    ],
)
def test_base_endpoint_contracts(client, call, expected):
    call(client)
    method, path, kwargs = expected
    client.request.assert_called_once_with(method, path, api_version="1.0", **kwargs)


def test_create_supports_current_pool_fields(client):
    spec = {"placement": {"labels": ["mds"]}}
    cephfs.create(client, "archive", spec, "archive-data", "archive-meta")
    client.request.assert_called_once_with(
        "POST",
        "/api/cephfs",
        api_version="1.0",
        data={
            "name": "archive",
            "service_spec": spec,
            "data_pool": "archive-data",
            "metadata_pool": "archive-meta",
        },
    )


def test_authorize_copies_caps_and_does_not_insert_root_squash_locally(client):
    caps = ["/", "rw", "/restricted", "r"]
    cephfs.authorize(client, "archive", "client.backup", caps, True)
    assert caps == ["/", "rw", "/restricted", "r"]
    assert client.request.call_args.kwargs["data"] == {
        "fs_name": "archive",
        "client_id": "client.backup",
        "caps": caps,
        "root_squash": True,
    }


@pytest.mark.parametrize(
    "call",
    [
        lambda c: cephfs.get(c, True),
        lambda c: cephfs.make_directory(c, 1, "relative"),
        lambda c: cephfs.set_quota(c, 1, "/"),
        lambda c: cephfs.authorize(c, "fs", "client.a", ["/", "rw", "/dangling"]),
        lambda c: cephfs.create(c, "fs", {}),
    ],
)
def test_invalid_base_arguments_fail_before_http(client, call):
    with pytest.raises(ConfigurationError):
        call(client)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "call",
    [
        lambda c: cephfs.remove(c, "archive"),
        lambda c: cephfs.rename(c, "archive", "renamed"),
        lambda c: cephfs.evict_client(c, 1, 2),
        lambda c: cephfs.remove_directory(c, 1, "/archive"),
        lambda c: cephfs.write_file(c, 1, "/archive/file", "contents"),
        lambda c: cephfs.unlink(c, 1, "/archive/file"),
        lambda c: cephfs.remove_snapshot(c, 1, "/archive", "daily"),
        lambda c: cephfs.rename_path(c, 1, "/archive", "/renamed"),
        lambda c: cephfs_volumes.subvolume_remove(c, "archive", "data"),
        lambda c: cephfs_volumes.group_remove(c, "archive", "tenants"),
        lambda c: cephfs_volumes.snapshot_remove(c, "archive", "data", "daily"),
        lambda c: cephfs_schedule.update(c, "archive", "/data", retention_to_remove="7-d"),
        lambda c: cephfs_schedule.remove(c, "archive", "/data", "1h", "2026-01-01T00:00:00"),
        lambda c: cephfs_mirror.disable(c, "archive"),
        lambda c: cephfs_mirror.remove_peer(c, "archive", "7b7ee9ec-0dcb-4e1f-a93d-01ecfa19562b"),
        lambda c: cephfs_mirror.remove_directory(c, "archive", "/data"),
        lambda c: cephfs_mirror.remove_checkpoint(c, "archive", "/data", "daily"),
    ],
)
def test_destructive_raw_calls_require_confirmation_before_http(client, call):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        call(client)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "call",
    [
        lambda c: cephfs.remove(c, "archive", confirm="yes"),
        lambda c: cephfs_volumes.subvolume_remove(c, "archive", "data", confirm=1),
        lambda c: cephfs_schedule.remove(
            c,
            "archive",
            "/data",
            "1h",
            "2026-01-01T00:00:00",
            confirm=None,
        ),
        lambda c: cephfs_mirror.remove_directory(c, "archive", "/data", confirm=1),
    ],
)
def test_destructive_raw_calls_reject_non_boolean_confirmation(client, call):
    with pytest.raises(ConfigurationError, match="boolean"):
        call(client)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "call",
    [
        lambda c: cephfs.remove(c, "archive", confirm=True),
        lambda c: cephfs.rename(c, "archive", "renamed", confirm=True),
        lambda c: cephfs.evict_client(c, 1, 2, confirm=True),
        lambda c: cephfs.remove_directory(c, 1, "/archive", confirm=True),
        lambda c: cephfs.write_file(c, 1, "/archive/file", "contents", confirm=True),
        lambda c: cephfs.unlink(c, 1, "/archive/file", confirm=True),
        lambda c: cephfs.remove_snapshot(c, 1, "/archive", "daily", confirm=True),
        lambda c: cephfs.rename_path(c, 1, "/archive", "/renamed", confirm=True),
        lambda c: cephfs_volumes.subvolume_remove(c, "archive", "data", confirm=True),
        lambda c: cephfs_volumes.group_remove(c, "archive", "tenants", confirm=True),
        lambda c: cephfs_volumes.snapshot_remove(c, "archive", "data", "daily", confirm=True),
        lambda c: cephfs_schedule.update(
            c, "archive", "/data", retention_to_remove="7-d", confirm=True
        ),
        lambda c: cephfs_schedule.remove(
            c,
            "archive",
            "/data",
            "1h",
            "2026-01-01T00:00:00",
            confirm=True,
        ),
        lambda c: cephfs_mirror.disable(c, "archive", confirm=True),
        lambda c: cephfs_mirror.remove_peer(
            c,
            "archive",
            "7b7ee9ec-0dcb-4e1f-a93d-01ecfa19562b",
            confirm=True,
        ),
        lambda c: cephfs_mirror.remove_directory(c, "archive", "/data", confirm=True),
        lambda c: cephfs_mirror.remove_checkpoint(c, "archive", "/data", "daily", confirm=True),
    ],
)
def test_explicit_confirmation_allows_destructive_raw_request(client, call):
    call(client)
    client.request.assert_called_once()


def test_subvolume_and_snapshot_contracts(client):
    cephfs_volumes.subvolume_create(
        client,
        "archive",
        "backup",
        {"size": 1024, "group_name": "nightly", "namespace_isolated": True},
    )
    assert client.request.call_args.kwargs["data"] == {
        "vol_name": "archive",
        "subvol_name": "backup",
        "size": 1024,
        "group_name": "nightly",
        "namespace_isolated": True,
    }
    client.reset_mock()
    cephfs_volumes.snapshot_remove(
        client,
        "archive",
        "backup",
        "daily-1",
        group_name="nightly",
        force=False,
        confirm=True,
    )
    client.request.assert_called_once_with(
        "DELETE",
        "/api/cephfs/subvolume/snapshot/archive/backup",
        api_version="1.0",
        params={"snap_name": "daily-1", "group_name": "nightly", "force": False},
    )


def test_snapshot_visibility_uses_current_ceph_endpoint(client):
    cephfs_volumes.set_snapshot_visibility(client, "archive", "backup", True)
    client.request.assert_called_once_with(
        "PUT",
        "/api/cephfs/subvolume/archive/snapshot-visibility",
        api_version="1.0",
        data={"subvol_name": "backup", "value": "true"},
    )


def test_extra_options_cannot_replace_explicit_arguments(client):
    with pytest.raises(ConfigurationError, match="explicit"):
        cephfs_volumes.subvolume_create(client, "archive", "backup", {"vol_name": "other"})
    client.request.assert_not_called()


def test_schedule_path_is_encoded_as_one_route_segment(client):
    cephfs_schedule.update(client, "archive", "/projects/nightly", "7-d", "12-h", confirm=True)
    client.request.assert_called_once_with(
        "PUT",
        "/api/cephfs/snapshot/schedule/archive/%2Fprojects%2Fnightly",
        api_version="1.0",
        data={"retention_to_add": "7-d", "retention_to_remove": "12-h"},
    )


@pytest.mark.parametrize("retention", ["7", "7-", "-d", "0-d", "7-z", "7-d|bad"])
def test_invalid_retention_fails_before_http(client, retention):
    with pytest.raises(ConfigurationError):
        cephfs_schedule.create(client, "archive", "/", "1h", "2026-01-01", retention)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "schedule,start", [("0h", "2026-01-01"), ("1z", "2026-01-01"), ("1h", "now")]
)
def test_invalid_schedule_identity_fails_before_http(client, schedule, start):
    with pytest.raises(ConfigurationError):
        cephfs_schedule.create(client, "archive", "/", schedule, start)
    client.request.assert_not_called()


def test_mirror_contracts(client):
    cephfs_mirror.directory_list(client, "archive")
    client.request.assert_called_once_with(
        "GET", "/api/cephfs/mirror/directory/archive", api_version="1.0"
    )
    client.reset_mock()
    cephfs_mirror.status(
        client,
        "archive",
        path="/projects",
        peer_uuid="7b7ee9ec-0dcb-4e1f-a93d-01ecfa19562b",
    )
    assert client.request.call_args.kwargs["params"] == {
        "path": "/projects",
        "peer_id": "7b7ee9ec-0dcb-4e1f-a93d-01ecfa19562b",
    }


def test_mirror_token_requires_expected_response_shape(client):
    client.request.return_value = APIResponse(200, {"unexpected": True})
    with pytest.raises(ProtocolError):
        cephfs_mirror.create_token(client, "archive", "client.mirror", "remote")


def test_mirror_token_file_operations_never_return_secret(tmp_path, monkeypatch):
    token = "private-bootstrap-token"
    client = Mock()
    monkeypatch.setattr(cephfs_api.ceph, "get_client", Mock(return_value=client))
    monkeypatch.setattr(
        cephfs_api.cephfs_mirror,
        "create_token",
        Mock(return_value=APIResponse(200, {"token": token})),
    )
    destination = tmp_path / "mirror.token"
    result = cephfs_api.mirror_create_token(
        {}, {}, {}, "archive", "client.mirror", "remote", destination
    )
    assert destination.read_text() == token
    assert token not in repr(result)
    assert result["data"]["destination"] == str(destination)


def test_mirror_peer_import_reads_token_without_returning_it(tmp_path, monkeypatch):
    token = "private-bootstrap-token"
    source = tmp_path / "mirror.token"
    source.write_text(token)
    client = Mock()
    add_peer = Mock(return_value=APIResponse(200, {"peer_uuid": "uuid"}))
    monkeypatch.setattr(cephfs_api.ceph, "get_client", Mock(return_value=client))
    monkeypatch.setattr(cephfs_api.cephfs_mirror, "add_peer", add_peer)
    result = cephfs_api.mirror_add_peer({}, {}, {}, "archive", source)
    add_peer.assert_called_once_with(client, "archive", token)
    assert token not in repr(result)
    assert result["data"] == {"filesystem": "archive", "source": str(source)}


def test_write_file_api_requires_confirmation_before_reading_source(monkeypatch):
    read_text = Mock()
    monkeypatch.setattr(cephfs_api.local_file, "read_text", read_text)
    with pytest.raises(ConfigurationError, match="confirm=True"):
        cephfs_api.write_file({}, {}, {}, 1, "/data/file", "C:/secret.txt")
    read_text.assert_not_called()
