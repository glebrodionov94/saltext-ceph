"""Unit tests for declarative CephFS state resources."""

from unittest.mock import Mock

import pytest

from saltext.ceph.states import cephfs as state


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def task(name="cephfs/mutate"):
    return envelope({"name": name, "metadata": {"fs_name": "archive"}}, status=202)


def filesystem():
    return {"id": 1, "mdsmap": {"fs_name": "archive"}}


def mds_daemon(name="mds.archive.node1.abcd"):
    return {"daemon_type": "mds", "daemon_name": name}


def directory(path="/data", snapshots=None, max_bytes=0, max_files=0):
    return {
        "name": path.rsplit("/", 1)[-1] or "/",
        "path": path,
        "parent": path.rsplit("/", 1)[0] or "/",
        "snapshots": [] if snapshots is None else snapshots,
        "quotas": {"max_bytes": max_bytes, "max_files": max_files},
    }


def subvolume(size=1024):
    return {"name": "data", "info": {"bytes_quota": size, "path": "/volumes/data"}}


def group(size=4096):
    return {"name": "tenants", "info": {"bytes_quota": size}}


def schedule(retention=None, active=True):
    return {
        "fs": "archive",
        "subvol": None,
        "group": None,
        "path": "/data",
        "rel_path": "/data",
        "schedule": "1h",
        "start": "2026-01-01T00:00:00",
        "retention": {} if retention is None else retention,
        "active": active,
    }


PEER_UUID = "7b7ee9ec-0dcb-4e1f-a93d-01ecfa19562b"


def peer(client_name="client.mirror", remote_filesystem="backup"):
    return {
        PEER_UUID: {
            "client_name": client_name,
            "site_name": "remote-site",
            "fs_name": remote_filesystem,
        }
    }


@pytest.fixture(autouse=True)
def globals_(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def test_virtual_requires_the_complete_execution_surface(monkeypatch):
    monkeypatch.setattr(state, "__salt__", {"cephfs.list": Mock()})
    result = state.__virtual__()
    assert result[0] is False
    assert "cephfs.create" in result[1]


def test_filesystem_present_is_idempotent_for_existence_projection(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.list": Mock(return_value=envelope([filesystem()])), "cephfs.create": create},
    )
    result = state.filesystem_present(
        "archive", {"placement": {"hosts": ["node1"]}}, data_pool="archive-data"
    )
    assert result["result"] is True
    assert not result["changes"]
    create.assert_not_called()


def test_filesystem_present_test_mode_has_exact_public_diff(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.list": Mock(return_value=envelope([])), "cephfs.create": create},
    )
    result = state.filesystem_present("archive", {"placement": {}})
    assert result["result"] is None
    assert result["changes"] == {"old": None, "new": {"filesystem": "archive"}}
    create.assert_not_called()


def test_filesystem_present_waits_for_202_and_post_reads(monkeypatch):
    listing = Mock(side_effect=[envelope([]), envelope([filesystem()])])
    create = Mock(return_value=task())
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.list": listing, "cephfs.create": create, "ceph_task.wait": wait},
    )
    result = state.filesystem_present("archive", {"placement": {"label": "mds"}})
    assert result["result"] is True
    assert result["changes"]["old"] is None
    assert result["changes"]["new"] == {"filesystem": "archive"}
    wait.assert_called_once()
    assert listing.call_count == 2


def test_filesystem_absent_requires_confirmation_but_test_mode_previews(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.list": Mock(return_value=envelope([filesystem()])), "cephfs.remove": remove},
    )
    result = state.filesystem_absent("archive")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    remove.assert_not_called()
    monkeypatch.setattr(state, "__opts__", {"test": True})
    result = state.filesystem_absent("archive")
    assert result["result"] is None
    remove.assert_not_called()


def test_filesystem_absent_waits_and_verifies_removal(monkeypatch):
    listing = Mock(side_effect=[envelope([filesystem()]), envelope([])])
    remove = Mock(return_value=task("cephfs/remove"))
    wait = Mock(return_value=envelope({"success": True}))
    daemons = Mock(return_value=envelope([]))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.list": listing,
            "cephfs.remove": remove,
            "ceph_service.daemons": daemons,
            "ceph_task.wait": wait,
        },
    )
    result = state.filesystem_absent("archive", confirm=True)
    assert result["result"] is True
    assert result["changes"]["new"] is None
    remove.assert_called_once_with("archive", confirm=True, profile="default")
    daemons.assert_called_once_with("mds.archive", profile="default")
    wait.assert_called_once()


def test_filesystem_absent_waits_for_stale_mds_daemon_cache(monkeypatch):
    listing = Mock(
        side_effect=[
            envelope([filesystem()]),
            envelope([]),
            envelope([]),
        ]
    )
    daemons = Mock(side_effect=[envelope([mds_daemon()]), envelope([])])
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.list": listing,
            "cephfs.remove": Mock(return_value=envelope(status=204)),
            "ceph_service.daemons": daemons,
        },
    )

    result = state.filesystem_absent(
        "archive",
        confirm=True,
        task_timeout=5,
        task_interval=1,
    )

    assert result["result"] is True
    assert result["changes"] == {"old": {"filesystem": "archive"}, "new": None}
    sleep.assert_called_once_with(1.0)


def test_filesystem_absent_rechecks_orphaned_mds_daemons_on_idempotent_run(monkeypatch):
    daemons = Mock(side_effect=[envelope([mds_daemon()]), envelope([])])
    sleep = Mock()
    monkeypatch.setattr(state.reconcile.time, "monotonic", Mock(side_effect=[0.0, 0.0]))
    monkeypatch.setattr(state.reconcile.time, "sleep", sleep)
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.list": Mock(return_value=envelope([])),
            "ceph_service.daemons": daemons,
        },
    )

    result = state.filesystem_absent("archive", task_timeout=5, task_interval=1)

    assert result["result"] is True
    assert not result["changes"]
    assert daemons.call_count == 2
    sleep.assert_not_called()


def test_filesystem_absent_test_mode_reports_pending_mds_daemon_convergence(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.list": Mock(return_value=envelope([])),
            "ceph_service.daemons": Mock(return_value=envelope([mds_daemon()])),
        },
    )

    result = state.filesystem_absent("archive")

    assert result["result"] is None
    assert result["changes"] == {"old": {"mds_daemons": ["mds.archive.node1.abcd"]}, "new": None}
    assert "would be awaited" in result["comment"]


def test_filesystem_async_without_waiter_fails_without_claiming_change(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.list": Mock(return_value=envelope([])),
            "cephfs.create": Mock(return_value=task()),
        },
    )
    result = state.filesystem_present("archive", {"placement": {}})
    assert result["result"] is False
    assert not result["changes"]
    assert "ceph_task.wait" in result["comment"]


def test_directory_present_noop_uses_exact_quota_projection(monkeypatch):
    set_quota = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.list_directories": Mock(
                return_value=envelope([directory(max_bytes=1024, max_files=12)])
            ),
            "cephfs.set_quota": set_quota,
        },
    )
    result = state.directory_present("/data", 1, max_bytes=1024, max_files=12)
    assert result["result"] is True
    assert not result["changes"]
    set_quota.assert_not_called()


def test_directory_present_creates_sets_quota_and_post_reads(monkeypatch):
    listing = Mock(
        side_effect=[
            envelope([]),
            envelope([directory(max_bytes=0)]),
            envelope([directory(max_bytes=1024)]),
        ]
    )
    make = Mock(return_value=task("cephfs/mkdir"))
    quota = Mock(return_value=envelope(status=200))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.list_directories": listing,
            "cephfs.make_directory": make,
            "cephfs.set_quota": quota,
            "ceph_task.wait": wait,
        },
    )
    result = state.directory_present("/data", "1", max_bytes=1024)
    assert result["result"] is True
    assert result["changes"]["old"] is None
    quota.assert_called_once_with("1", "/data", max_bytes=1024, max_files=None, profile="default")
    assert wait.call_count == 1


def test_directory_absent_rejects_root_and_guards_live_delete(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.root_directory": Mock(return_value=envelope(directory("/"))),
            "cephfs.list_directories": Mock(return_value=envelope([directory()])),
            "cephfs.remove_directory": remove,
        },
    )
    assert "cannot be removed" in state.directory_absent("/", 1, confirm=True)["comment"]
    result = state.directory_absent("/data", 1)
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    remove.assert_not_called()


def test_directory_quota_reduction_requires_confirmation(monkeypatch):
    quota = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.list_directories": Mock(return_value=envelope([directory(max_bytes=2048)])),
            "cephfs.set_quota": quota,
        },
    )
    result = state.directory_present("/data", 1, max_bytes=1024)
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    quota.assert_not_called()


def test_directory_snapshot_create_and_delete_are_post_read(monkeypatch):
    before = directory()
    after = directory(snapshots=[{"name": "daily", "created": "now"}])
    listing = Mock(
        side_effect=[
            envelope([before]),
            envelope([before]),
            envelope([after]),
            envelope([after]),
        ]
    )
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.list_directories": listing, "cephfs.create_snapshot": create},
    )
    result = state.directory_snapshot_present("daily", 1, "/data")
    assert result["result"] is True
    assert result["changes"]["old"] is None
    create.assert_called_once_with("1", "/data", snapshot_name="daily", profile="default")

    listing = Mock(side_effect=[envelope([after]), envelope([after])])
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.list_directories": listing, "cephfs.remove_snapshot": remove},
    )
    result = state.directory_snapshot_absent("daily", 1, "/data")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    remove.assert_not_called()


def test_subvolume_present_noop_for_size_and_visibility(monkeypatch):
    resize = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.subvolume_list": Mock(return_value=envelope([subvolume()])),
            "cephfs.snapshot_visibility": Mock(return_value=envelope("true")),
            "cephfs.subvolume_resize": resize,
        },
    )
    result = state.subvolume_present("data", "archive", size=1024, snapshot_visibility=True)
    assert result["result"] is True
    assert not result["changes"]
    resize.assert_not_called()


def test_subvolume_present_create_is_verified_and_does_not_expose_options(monkeypatch):
    listing = Mock(side_effect=[envelope([]), envelope([subvolume()]), envelope([subvolume()])])
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.subvolume_list": listing, "cephfs.subvolume_create": create},
    )
    result = state.subvolume_present("data", "archive", size=1024)
    assert result["result"] is True
    assert result["changes"]["old"] is None
    create.assert_called_once_with("archive", "data", options={"size": 1024}, profile="default")


def test_subvolume_quota_reduction_requires_confirmation(monkeypatch):
    resize = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.subvolume_list": Mock(return_value=envelope([subvolume(2048)])),
            "cephfs.subvolume_resize": resize,
        },
    )
    result = state.subvolume_present("data", "archive", size=1024)
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    resize.assert_not_called()


def test_subvolume_absent_test_mode_and_live_confirmation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.subvolume_list": Mock(return_value=envelope([subvolume()])),
            "cephfs.subvolume_remove": remove,
        },
    )
    result = state.subvolume_absent("data", "archive")
    assert result["result"] is None
    remove.assert_not_called()


def test_subvolume_group_create_and_snapshot_lifecycle(monkeypatch):
    groups = Mock(side_effect=[envelope([]), envelope([group()]), envelope([group()])])
    create_group = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.group_list": groups, "cephfs.group_create": create_group},
    )
    result = state.subvolume_group_present("tenants", "archive", size=4096)
    assert result["result"] is True
    create_group.assert_called_once_with(
        "archive", "tenants", options={"size": 4096}, profile="default"
    )

    snapshots = Mock(side_effect=[envelope([]), envelope([{"name": "daily"}])])
    create_snapshot = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.subvolume_snapshot_list": snapshots,
            "cephfs.subvolume_snapshot_create": create_snapshot,
        },
    )
    result = state.subvolume_snapshot_present("daily", "archive", "data")
    assert result["result"] is True
    create_snapshot.assert_called_once_with(
        "archive", "data", "daily", group_name=None, profile="default"
    )


def test_subvolume_snapshot_absent_requires_confirmation(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.subvolume_snapshot_list": Mock(return_value=envelope([{"name": "daily"}])),
            "cephfs.subvolume_snapshot_remove": remove,
        },
    )
    result = state.subvolume_snapshot_absent("daily", "archive", "data")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    remove.assert_not_called()


def test_schedule_present_is_idempotent_for_exact_policy(monkeypatch):
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.schedule_list": Mock(return_value=envelope([schedule({"d": 7}, active=True)])),
            "cephfs.schedule_update": update,
        },
    )
    result = state.snapshot_schedule_present(
        "/data",
        "archive",
        "1h",
        "2026-01-01T03:00:00+03:00",
        retention={"d": 7},
    )
    assert result["result"] is True
    assert not result["changes"]
    update.assert_not_called()


def test_schedule_retention_removal_is_previewable_and_guarded(monkeypatch):
    listing = Mock(return_value=envelope([schedule({"d": 7, "h": 12})]))
    update = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.schedule_list": listing, "cephfs.schedule_update": update},
    )
    result = state.snapshot_schedule_present(
        "/data", "archive", "1h", "2026-01-01", retention={"d": 14}, active=None
    )
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    update.assert_not_called()
    monkeypatch.setattr(state, "__opts__", {"test": True})
    result = state.snapshot_schedule_present(
        "/data", "archive", "1h", "2026-01-01", retention={"d": 14}, active=None
    )
    assert result["result"] is None


def test_schedule_create_deactivates_and_post_reads(monkeypatch):
    listing = Mock(
        side_effect=[
            envelope([]),
            envelope([schedule(active=True)]),
            envelope([schedule(active=True)]),
            envelope([schedule(active=False)]),
        ]
    )
    create = Mock(return_value=envelope(status=201))
    deactivate = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.schedule_list": listing,
            "cephfs.schedule_create": create,
            "cephfs.schedule_deactivate": deactivate,
        },
    )
    result = state.snapshot_schedule_present("/data", "archive", "1h", "2026-01-01", active=False)
    assert result["result"] is True
    assert result["changes"]["old"] is None
    deactivate.assert_called_once()


def test_schedule_absent_requires_confirmation_before_mutation(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.schedule_list": Mock(return_value=envelope([schedule({"d": 7})])),
            "cephfs.schedule_remove": remove,
        },
    )
    result = state.snapshot_schedule_absent("/data", "archive", "1h", "2026-01-01")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    remove.assert_not_called()


def test_schedule_absent_cleans_last_policy_and_post_reads(monkeypatch):
    listing = Mock(side_effect=[envelope([schedule({"d": 7})]), envelope([])])
    remove = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.schedule_list": listing, "cephfs.schedule_remove": remove},
    )
    result = state.snapshot_schedule_absent("/data", "archive", "1h", "2026-01-01", confirm=True)
    assert result["result"] is True
    remove.assert_called_once_with(
        "archive",
        "/data",
        "1h",
        "2026-01-01T00:00:00",
        retention_policy="7-d",
        subvolume=None,
        group_name=None,
        confirm=True,
        profile="default",
    )


def test_mirror_directory_present_and_absent_use_exact_path_list(monkeypatch):
    listing = Mock(side_effect=[envelope([]), envelope(["/data"])])
    add = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.mirror_directory_list": listing, "cephfs.mirror_add_directory": add},
    )
    result = state.mirror_directory_present("/data", "archive")
    assert result["result"] is True
    assert result["changes"]["new"] == {"filesystem": "archive", "path": "/data"}

    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.mirror_directory_list": Mock(return_value=envelope(["/data"])),
            "cephfs.mirror_remove_directory": remove,
        },
    )
    result = state.mirror_directory_absent("/data", "archive")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    remove.assert_not_called()


def test_mirror_peer_test_mode_validates_source_without_exposing_it(tmp_path, monkeypatch):
    token = "super-private-bootstrap-token"
    source = tmp_path / "peer.token"
    source.write_text(token, encoding="utf-8")
    monkeypatch.setattr(state, "__opts__", {"test": True})
    add = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.mirror_peer_list": Mock(return_value=envelope([])), "cephfs.mirror_add_peer": add},
    )
    result = state.mirror_peer_present(
        "remote-site",
        "archive",
        source=str(source),
        client_name="client.mirror",
        remote_filesystem="backup",
    )
    assert result["result"] is None
    assert token not in repr(result)
    assert str(source) not in repr(result)
    add.assert_not_called()


def test_mirror_peer_import_post_reads_and_redacts_source(tmp_path, monkeypatch):
    source = tmp_path / "peer.token"
    source.write_text("private-token", encoding="utf-8")
    listing = Mock(side_effect=[envelope([]), envelope([peer()])])
    add = Mock(return_value=envelope({"peer_uuid": PEER_UUID}, status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.mirror_peer_list": listing, "cephfs.mirror_add_peer": add},
    )
    result = state.mirror_peer_present(
        "remote-site",
        "archive",
        source=str(source),
        client_name="client.mirror",
        remote_filesystem="backup",
    )
    assert result["result"] is True
    assert str(source) not in repr(result)
    assert "private-token" not in repr(result)
    add.assert_called_once_with("archive", str(source), profile="default")


def test_mirror_peer_create_only_drift_fails_without_mutation(monkeypatch):
    add = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.mirror_peer_list": Mock(return_value=envelope([peer()])),
            "cephfs.mirror_add_peer": add,
        },
    )
    result = state.mirror_peer_present("remote-site", "archive", client_name="client.other")
    assert result["result"] is False
    assert "create-only" in result["comment"]
    add.assert_not_called()


def test_mirror_peer_absent_requires_confirmation(monkeypatch):
    remove = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "cephfs.mirror_peer_list": Mock(return_value=envelope([peer()])),
            "cephfs.mirror_remove_peer": remove,
        },
    )
    result = state.mirror_peer_absent("remote-site", "archive")
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    remove.assert_not_called()


def test_mirror_peer_absent_deletes_uuid_and_post_reads(monkeypatch):
    listing = Mock(side_effect=[envelope([peer()]), envelope([])])
    remove = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.mirror_peer_list": listing, "cephfs.mirror_remove_peer": remove},
    )
    result = state.mirror_peer_absent("remote-site", "archive", confirm=True)
    assert result["result"] is True
    remove.assert_called_once_with("archive", PEER_UUID, confirm=True, profile="default")


def test_malformed_public_response_fails_safely(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {"cephfs.mirror_peer_list": Mock(return_value=envelope([{"bad": "shape"}]))},
    )
    result = state.mirror_peer_absent("remote-site", "archive", confirm=True)
    assert result["result"] is False
    assert not result["changes"]
    assert "unexpected shape" in result["comment"]
