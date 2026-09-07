"""Destructive opt-in lifecycle tests for durable Ceph storage states.

Every identity comes from an explicit environment variable and must also be in
``CEPH_TEST_DESTRUCTIVE_ALLOWLIST``.  Each test proves that its exact resources
are absent before taking a runtime infrastructure lease.  Cleanup runs only for
objects created after that proof and validates the strongest ownership signal
the Dashboard read model exposes before deleting in reverse dependency order.
"""

import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from saltext.ceph.states import ceph_pool as pool_state
from saltext.ceph.states import ceph_rbd as rbd_state
from saltext.ceph.states import ceph_rgw_bucket as rgw_bucket_state
from saltext.ceph.states import ceph_rgw_user as rgw_user_state
from saltext.ceph.states import ceph_service as service_state
from saltext.ceph.states import cephfs as cephfs_state
from saltext.ceph.utils.ceph import cephfs as cephfs_resource
from saltext.ceph.utils.ceph import cluster_configuration
from saltext.ceph.utils.ceph import host as host_resource
from saltext.ceph.utils.ceph import osd as osd_resource
from saltext.ceph.utils.ceph import pool as pool_resource
from saltext.ceph.utils.ceph import rbd as rbd_resource
from saltext.ceph.utils.ceph import rgw_bucket as rgw_bucket_resource
from saltext.ceph.utils.ceph import rgw_daemon as rgw_daemon_resource
from saltext.ceph.utils.ceph import rgw_user as rgw_user_resource
from saltext.ceph.utils.ceph import service as service_resource
from saltext.ceph.utils.ceph.errors import APIError

from ._storage_live import assert_changed
from ._storage_live import assert_current
from ._storage_live import assert_plan
from ._storage_live import bind_cephfs_state
from ._storage_live import bind_pool_state
from ._storage_live import bind_rbd_state
from ._storage_live import bind_rgw_bucket_state
from ._storage_live import bind_rgw_user_state
from ._storage_live import required_identity

pytestmark = pytest.mark.ceph_live

_PROFILE = "live"
_POOL_OWNER_APPLICATION = "saltext_ci_owned"
_POOL_UPDATED_APPLICATION = "saltext_ci_updated"
_RBD_OWNER_KEY = "saltext.ci.owner"
_MIB = 1024 * 1024
_POOL_OPTIONS = {"size": 3, "min_size": 2, "pg_autoscale_mode": "off"}
_RGW_READY_RETRY_STATUSES = frozenset((404, 500, 503))


@dataclass(frozen=True)
class _RgwLifecycleResources:
    service_name: str
    service_host: str
    uid: str
    owner_marker: str
    bucket: str
    daemon_name: str | None


def _has_osd_state(item, state):
    states = item.get("state")
    return item.get(state) in (True, 1) or (isinstance(states, list) and state in states)


def _require_up_osds(live_client, minimum=3):
    items = osd_resource.list_(live_client).data
    ready = [
        item
        for item in items
        if isinstance(item, Mapping) and _has_osd_state(item, "up") and _has_osd_state(item, "in")
    ]
    if len(ready) < minimum:
        pytest.skip(f"requires at least {minimum} up/in OSD(s); provision storage first")
    return ready


def _effective_config(live_client, name, sections=("global",)):
    current = cluster_configuration.get(live_client, name).data
    values = current.get("value")
    if isinstance(values, list):
        for section in sections:
            for item in reversed(values):
                if isinstance(item, Mapping) and item.get("section") == section:
                    return item.get("value")
    return current.get("default")


def _require_storage_baseline(live_client):
    _require_up_osds(live_client)
    delete_enabled = _effective_config(
        live_client,
        "mon_allow_pool_delete",
        sections=("mon", "global"),
    )
    if str(delete_enabled).casefold() != "true":
        pytest.skip("storage lifecycle requires mon_allow_pool_delete=true")


def _pool(live_client, name):
    items = pool_resource.list_(live_client).data
    matches = [item for item in items if item.get("pool_name") == name]
    if len(matches) > 1:
        pytest.fail(f"pool inventory returned duplicate identity {name}")
    return matches[0] if matches else None


def _owned_pool(live_client, name):
    if _pool(live_client, name) is None:
        return None
    current = pool_resource.get(live_client, name).data
    applications = current.get("application_metadata")
    if not isinstance(applications, list) or _POOL_OWNER_APPLICATION not in applications:
        pytest.fail(f"refusing to delete pool {name}: ownership application is absent")
    return current


def _image(live_client, image_spec):
    try:
        return rbd_resource.get(live_client, image_spec).data
    except APIError as exc:
        if exc.status == 404:
            return None
        raise


def _owned_image(live_client, image_spec, marker):
    current = _image(live_client, image_spec)
    if current is None:
        return None
    metadata = current.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get(_RBD_OWNER_KEY) not in (
        marker,
        f"{marker}:updated",
    ):
        pytest.fail(f"refusing to delete RBD image {image_spec}: ownership metadata differs")
    return current


def _namespace(live_client, pool_name, namespace):
    items = rbd_resource.namespace_list(live_client, pool_name).data
    matches = [item for item in items if item.get("namespace") == namespace]
    if len(matches) > 1:
        pytest.fail(f"RBD namespace inventory returned duplicate identity {namespace}")
    return matches[0] if matches else None


def _filesystem(live_client, name):
    matches = []
    for item in cephfs_resource.list_(live_client).data:
        if not isinstance(item, Mapping):
            pytest.fail("CephFS inventory returned a non-mapping entry")
        item_name = item.get("name")
        if item_name is None and isinstance(item.get("mdsmap"), Mapping):
            item_name = item["mdsmap"].get("fs_name")
        if item_name == name:
            matches.append(item)
    if len(matches) > 1:
        pytest.fail(f"CephFS inventory returned duplicate identity {name}")
    return matches[0] if matches else None


def _host(live_client, name):
    matches = [
        item
        for item in host_resource.list_(live_client, sources=["orchestrator"]).data
        if item.get("hostname") == name
    ]
    if len(matches) > 1:
        pytest.fail(f"host inventory returned duplicate identity {name}")
    return matches[0] if matches else None


def _named_item(items, name, label):
    matches = [item for item in items if isinstance(item, Mapping) and item.get("name") == name]
    if len(matches) > 1:
        pytest.fail(f"{label} inventory returned duplicate identity {name}")
    return matches[0] if matches else None


def _rgw_user(live_client, uid, daemon_name):
    users = rgw_user_resource.list_users(live_client, daemon_name=daemon_name).data
    if users.count(uid) > 1:
        pytest.fail(f"RGW user inventory returned duplicate identity {uid}")
    return (
        None
        if uid not in users
        else rgw_user_resource.get_user(
            live_client,
            uid,
            daemon_name=daemon_name,
        ).data
    )


def _owned_rgw_user(live_client, uid, marker, daemon_name):
    current = _rgw_user(live_client, uid, daemon_name)
    if current is None:
        return None
    if current.get("display_name") not in (marker, f"{marker}:updated"):
        pytest.fail(f"refusing to delete RGW user {uid}: ownership display name differs")
    return current


def _rgw_bucket(live_client, name, daemon_name):
    buckets = rgw_bucket_resource.list_buckets(
        live_client,
        daemon_name=daemon_name,
    ).data
    if buckets.count(name) > 1:
        pytest.fail(f"RGW bucket inventory returned duplicate identity {name}")
    return (
        None
        if name not in buckets
        else rgw_bucket_resource.get_bucket(
            live_client,
            name,
            daemon_name=daemon_name,
        ).data
    )


def _owned_rgw_bucket(live_client, name, uid, daemon_name):
    current = _rgw_bucket(live_client, name, daemon_name)
    if current is None:
        return None
    if current.get("owner") != uid:
        pytest.fail(f"refusing to delete RGW bucket {name}: owner differs")
    return current


def _service(live_client, name):
    matches = [
        item
        for item in service_resource.list_(live_client, service_name=name).data
        if item.get("service_name") == name
    ]
    if len(matches) > 1:
        pytest.fail(f"service inventory returned duplicate identity {name}")
    return matches[0] if matches else None


def _owned_service(live_client, name, host):
    if _service(live_client, name) is None:
        return None
    current = service_resource.get(live_client, name).data
    placement = current.get("placement")
    if not isinstance(placement, Mapping) or host not in placement.get("hosts", []):
        pytest.fail(f"refusing to delete service {name}: exact placement host differs")
    return current


def _cleanup_rgw_resources(live_client, resources, claims_proven, confirmed_absent):
    """Remove only claimed RGW resources whose absence was not already confirmed."""
    if claims_proven and "bucket" not in confirmed_absent:
        if resources.daemon_name is None:
            pytest.fail("claimed RGW resources have no selected daemon")
        if (
            _owned_rgw_bucket(
                live_client,
                resources.bucket,
                resources.uid,
                resources.daemon_name,
            )
            is not None
        ):
            result = rgw_bucket_state.absent(
                resources.bucket,
                daemon_name=resources.daemon_name,
                confirm=True,
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert result["result"] is True, result["comment"]
    if claims_proven and "user" not in confirmed_absent:
        if resources.daemon_name is None:
            pytest.fail("claimed RGW resources have no selected daemon")
        if (
            _owned_rgw_user(
                live_client,
                resources.uid,
                resources.owner_marker,
                resources.daemon_name,
            )
            is not None
        ):
            result = rgw_user_state.absent(
                resources.uid,
                daemon_name=resources.daemon_name,
                confirm=True,
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert result["result"] is True, result["comment"]
    if "service" not in confirmed_absent and (
        _owned_service(live_client, resources.service_name, resources.service_host) is not None
    ):
        result = service_state.absent(
            resources.service_name,
            confirm=True,
            profile=_PROFILE,
            task_interval=0.5,
        )
        assert result["result"] is True, result["comment"]


def _wait_for_running_service(live_client, name, timeout=600.0):
    deadline = time.monotonic() + timeout
    while True:
        try:
            daemons = service_resource.daemons(live_client, name).data
        except APIError as exc:
            if exc.status not in (404, 503) or time.monotonic() >= deadline:
                raise
            daemons = []
        if any(
            isinstance(item, Mapping)
            and isinstance(item.get("daemon_name"), str)
            and (item.get("status") in (1, "running") or item.get("status_desc") == "running")
            for item in daemons
        ):
            return
        if time.monotonic() >= deadline:
            pytest.fail(f"service {name} did not report a running daemon before timeout")
        time.sleep(2.0)


def _rgw_daemon_for_service(daemons, service_name, service_host):
    """Select the one daemon whose Ceph identity belongs to this ServiceSpec."""
    service_type, separator, service_id = service_name.partition(".")
    if service_type != "rgw" or not separator or not service_id:
        pytest.fail(f"invalid RGW service identity {service_name}")

    def belongs_to_service(value):
        return isinstance(value, str) and any(
            value == prefix or value.startswith(f"{prefix}.")
            for prefix in (service_id, service_name)
        )

    matches = []
    for daemon in daemons:
        if not isinstance(daemon, Mapping):
            pytest.fail("RGW daemon inventory returned a non-mapping entry")
        if daemon.get("server_hostname") != service_host:
            continue
        if belongs_to_service(daemon.get("id")) or belongs_to_service(daemon.get("service_map_id")):
            daemon_id = daemon.get("id")
            if not isinstance(daemon_id, str) or not daemon_id:
                pytest.fail("matching RGW daemon has no public API identity")
            matches.append(daemon_id)
    if len(matches) > 1:
        pytest.fail(f"RGW service {service_name} reported multiple daemons on {service_host}")
    return matches[0] if matches else None


def _wait_for_rgw_ready(
    live_client,
    service_name,
    service_host,
    timeout=900.0,
    interval=5.0,
):
    """Wait until the exact daemon and its Dashboard Admin Ops client are usable."""
    deadline = time.monotonic() + timeout
    last_problem = "the exact RGW daemon is not visible"
    while True:
        try:
            daemons = rgw_daemon_resource.list_daemons(live_client).data
            daemon_name = _rgw_daemon_for_service(daemons, service_name, service_host)
            if daemon_name is None:
                last_problem = "the exact RGW daemon is not visible"
            else:
                try:
                    rgw_user_resource.list_users(
                        live_client,
                        daemon_name=daemon_name,
                    )
                except APIError as exc:
                    if exc.status not in _RGW_READY_RETRY_STATUSES:
                        raise
                    last_problem = f"/api/rgw/user returned HTTP {exc.status}"
                else:
                    return daemon_name
        except APIError as exc:
            if exc.status not in _RGW_READY_RETRY_STATUSES:
                raise
            last_problem = f"/api/rgw/daemon returned HTTP {exc.status}"

        now = time.monotonic()
        if now >= deadline:
            pytest.fail(
                f"RGW Admin Ops API for {service_name} did not become ready before timeout: "
                f"{last_problem}"
            )
        time.sleep(min(interval, deadline - now))


@pytest.mark.ceph_live_destructive
@pytest.mark.ceph_live_feature("rbd")
def test_live_pool_rbd_namespace_image_snapshot_lifecycle(
    monkeypatch,
    live_client,
):
    """Reconcile one isolated pool and its RBD resources in dependency order."""
    _require_storage_baseline(live_client)
    pool_name = required_identity("CEPH_TEST_POOL")
    namespace = required_identity("CEPH_TEST_RBD_NAMESPACE")
    image_name = required_identity("CEPH_TEST_RBD_IMAGE")
    snapshot = required_identity("CEPH_TEST_RBD_SNAPSHOT")
    image_spec = f"{pool_name}/{image_name}"
    owner_marker = f"saltext-ci-owner:{image_name}"
    resources = (
        f"pool:{pool_name}",
        f"namespace:{pool_name}/{namespace}",
        f"image:{image_spec}",
        f"snapshot:{image_spec}@{snapshot}",
    )
    pool_opts = bind_pool_state(monkeypatch, live_client, test=True)
    rbd_opts = bind_rbd_state(monkeypatch, live_client, test=True)

    if _pool(live_client, pool_name) is not None:
        pytest.fail(f"refusing to claim pre-existing pool {pool_name}")

    with live_client.infrastructure_lease(*resources):
        try:
            plan = pool_state.present(
                pool_name,
                8,
                "replicated",
                application_metadata=["rbd", _POOL_OWNER_APPLICATION],
                options=_POOL_OPTIONS,
                profile=_PROFILE,
            )
            assert_plan(plan)

            pool_opts["test"] = False
            created = pool_state.present(
                pool_name,
                8,
                "replicated",
                application_metadata=["rbd", _POOL_OWNER_APPLICATION],
                options=_POOL_OPTIONS,
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert_changed(created)
            created_pool = _pool(live_client, pool_name)
            assert created_pool["size"] == 3
            assert created_pool["min_size"] == 2
            assert_current(
                pool_state.present(
                    pool_name,
                    8,
                    "replicated",
                    application_metadata=["rbd", _POOL_OWNER_APPLICATION],
                    options=_POOL_OPTIONS,
                    profile=_PROFILE,
                )
            )

            pool_opts["test"] = True
            update_plan = pool_state.present(
                pool_name,
                8,
                "replicated",
                application_metadata=[
                    "rbd",
                    _POOL_OWNER_APPLICATION,
                    _POOL_UPDATED_APPLICATION,
                ],
                options=_POOL_OPTIONS,
                profile=_PROFILE,
            )
            assert update_plan["result"] is None, update_plan["comment"]

            pool_opts["test"] = False
            assert_changed(
                pool_state.present(
                    pool_name,
                    8,
                    "replicated",
                    application_metadata=[
                        "rbd",
                        _POOL_OWNER_APPLICATION,
                        _POOL_UPDATED_APPLICATION,
                    ],
                    options=_POOL_OPTIONS,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                pool_state.present(
                    pool_name,
                    8,
                    "replicated",
                    application_metadata=[
                        "rbd",
                        _POOL_OWNER_APPLICATION,
                        _POOL_UPDATED_APPLICATION,
                    ],
                    options=_POOL_OPTIONS,
                    profile=_PROFILE,
                )
            )

            if _namespace(live_client, pool_name, namespace) is not None:
                pytest.fail(f"refusing to claim pre-existing RBD namespace {namespace}")
            assert_plan(rbd_state.namespace_present(namespace, pool_name, profile=_PROFILE))
            rbd_opts["test"] = False
            assert_changed(
                rbd_state.namespace_present(
                    namespace,
                    pool_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(rbd_state.namespace_present(namespace, pool_name, profile=_PROFILE))

            if _image(live_client, image_spec) is not None:
                pytest.fail(f"refusing to claim pre-existing RBD image {image_spec}")
            rbd_opts["test"] = True
            assert_plan(
                rbd_state.image_present(
                    image_spec,
                    8 * _MIB,
                    features=["layering"],
                    metadata={_RBD_OWNER_KEY: owner_marker},
                    profile=_PROFILE,
                )
            )
            rbd_opts["test"] = False
            assert_changed(
                rbd_state.image_present(
                    image_spec,
                    8 * _MIB,
                    features=["layering"],
                    metadata={_RBD_OWNER_KEY: owner_marker},
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rbd_state.image_present(
                    image_spec,
                    8 * _MIB,
                    features=["layering"],
                    metadata={_RBD_OWNER_KEY: owner_marker},
                    profile=_PROFILE,
                )
            )

            rbd_opts["test"] = True
            update_plan = rbd_state.image_present(
                image_spec,
                8 * _MIB,
                features=["layering"],
                metadata={_RBD_OWNER_KEY: f"{owner_marker}:updated"},
                profile=_PROFILE,
            )
            assert update_plan["result"] is None, update_plan["comment"]
            rbd_opts["test"] = False
            assert_changed(
                rbd_state.image_present(
                    image_spec,
                    8 * _MIB,
                    features=["layering"],
                    metadata={_RBD_OWNER_KEY: f"{owner_marker}:updated"},
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rbd_state.image_present(
                    image_spec,
                    8 * _MIB,
                    features=["layering"],
                    metadata={_RBD_OWNER_KEY: f"{owner_marker}:updated"},
                    profile=_PROFILE,
                )
            )

            image = _owned_image(live_client, image_spec, owner_marker)
            if _named_item(image.get("snapshots", []), snapshot, "RBD snapshot") is not None:
                pytest.fail(f"refusing to claim pre-existing RBD snapshot {snapshot}")
            rbd_opts["test"] = True
            assert_plan(rbd_state.snapshot_present(snapshot, image_spec, profile=_PROFILE))
            rbd_opts["test"] = False
            assert_changed(
                rbd_state.snapshot_present(
                    snapshot,
                    image_spec,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(rbd_state.snapshot_present(snapshot, image_spec, profile=_PROFILE))

            rbd_opts["test"] = True
            delete_plan = rbd_state.snapshot_absent(snapshot, image_spec, profile=_PROFILE)
            assert delete_plan["result"] is None, delete_plan["comment"]
            rbd_opts["test"] = False
            refused = rbd_state.snapshot_absent(snapshot, image_spec, profile=_PROFILE)
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert_changed(
                rbd_state.snapshot_absent(
                    snapshot,
                    image_spec,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(rbd_state.snapshot_absent(snapshot, image_spec, profile=_PROFILE))

            rbd_opts["test"] = True
            assert rbd_state.image_absent(image_spec, profile=_PROFILE)["result"] is None
            rbd_opts["test"] = False
            assert_changed(
                rbd_state.image_absent(
                    image_spec,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(rbd_state.image_absent(image_spec, profile=_PROFILE))

            rbd_opts["test"] = True
            assert (
                rbd_state.namespace_absent(namespace, pool_name, profile=_PROFILE)["result"] is None
            )
            rbd_opts["test"] = False
            assert_changed(
                rbd_state.namespace_absent(
                    namespace,
                    pool_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(rbd_state.namespace_absent(namespace, pool_name, profile=_PROFILE))

            pool_opts["test"] = True
            assert pool_state.absent(pool_name, profile=_PROFILE)["result"] is None
            pool_opts["test"] = False
            assert_changed(
                pool_state.absent(
                    pool_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(pool_state.absent(pool_name, profile=_PROFILE))
        finally:
            rbd_opts["test"] = False
            pool_opts["test"] = False
            image = _owned_image(live_client, image_spec, owner_marker)
            if image is not None:
                if _named_item(image.get("snapshots", []), snapshot, "RBD snapshot") is not None:
                    result = rbd_state.snapshot_absent(
                        snapshot,
                        image_spec,
                        confirm=True,
                        profile=_PROFILE,
                        task_interval=0.5,
                    )
                    assert result["result"] is True, result["comment"]
                result = rbd_state.image_absent(
                    image_spec,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
                assert result["result"] is True, result["comment"]
            if _owned_pool(live_client, pool_name) is not None:
                if _namespace(live_client, pool_name, namespace) is not None:
                    result = rbd_state.namespace_absent(
                        namespace,
                        pool_name,
                        confirm=True,
                        profile=_PROFILE,
                        task_interval=0.5,
                    )
                    assert result["result"] is True, result["comment"]
                result = pool_state.absent(
                    pool_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
                assert result["result"] is True, result["comment"]


@pytest.mark.ceph_live_destructive
@pytest.mark.ceph_live_feature("cephfs")
def test_live_cephfs_pool_group_subvolume_snapshot_lifecycle(monkeypatch, live_client):
    """Create one three-replica CephFS stack, update quotas, then remove it safely."""
    _require_storage_baseline(live_client)
    filesystem = required_identity("CEPH_TEST_CEPHFS")
    filesystem_host = required_identity("CEPH_TEST_CEPHFS_HOST")
    data_pool = required_identity("CEPH_TEST_CEPHFS_DATA_POOL")
    metadata_pool = required_identity("CEPH_TEST_CEPHFS_METADATA_POOL")
    group = required_identity("CEPH_TEST_CEPHFS_GROUP")
    subvolume = required_identity("CEPH_TEST_CEPHFS_SUBVOLUME")
    snapshot = required_identity("CEPH_TEST_CEPHFS_SNAPSHOT")
    resources = (
        f"pool:{data_pool}",
        f"pool:{metadata_pool}",
        f"fs:{filesystem}",
        f"host:{filesystem_host}",
        f"cephfs-group:{filesystem}/{group}",
        f"cephfs-subvolume:{filesystem}/{group}/{subvolume}",
        f"cephfs-snapshot:{filesystem}/{group}/{subvolume}@{snapshot}",
    )
    pool_opts = bind_pool_state(monkeypatch, live_client, test=True)
    cephfs_opts = bind_cephfs_state(monkeypatch, live_client, test=True)
    service_spec = {"placement": {"hosts": [filesystem_host]}}

    for name in (data_pool, metadata_pool):
        if _pool(live_client, name) is not None:
            pytest.fail(f"refusing to claim pre-existing CephFS pool {name}")
    if _filesystem(live_client, filesystem) is not None:
        pytest.fail(f"refusing to claim pre-existing CephFS filesystem {filesystem}")
    if _host(live_client, filesystem_host) is None:
        pytest.fail(f"CephFS placement host {filesystem_host} is absent from the orchestrator")

    with live_client.infrastructure_lease(*resources):
        try:
            for name in (data_pool, metadata_pool):
                assert_plan(
                    pool_state.present(
                        name,
                        8,
                        "replicated",
                        application_metadata=["cephfs", _POOL_OWNER_APPLICATION],
                        options=_POOL_OPTIONS,
                        profile=_PROFILE,
                    )
                )
                pool_opts["test"] = False
                assert_changed(
                    pool_state.present(
                        name,
                        8,
                        "replicated",
                        application_metadata=["cephfs", _POOL_OWNER_APPLICATION],
                        options=_POOL_OPTIONS,
                        profile=_PROFILE,
                        task_interval=0.5,
                    )
                )
                created_pool = _pool(live_client, name)
                assert created_pool["size"] == 3
                assert created_pool["min_size"] == 2
                assert_current(
                    pool_state.present(
                        name,
                        8,
                        "replicated",
                        application_metadata=["cephfs", _POOL_OWNER_APPLICATION],
                        options=_POOL_OPTIONS,
                        profile=_PROFILE,
                    )
                )
                pool_opts["test"] = True

            assert_plan(
                cephfs_state.filesystem_present(
                    filesystem,
                    service_spec,
                    data_pool=data_pool,
                    metadata_pool=metadata_pool,
                    profile=_PROFILE,
                )
            )
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.filesystem_present(
                    filesystem,
                    service_spec,
                    data_pool=data_pool,
                    metadata_pool=metadata_pool,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.filesystem_present(
                    filesystem,
                    service_spec,
                    data_pool=data_pool,
                    metadata_pool=metadata_pool,
                    profile=_PROFILE,
                )
            )

            cephfs_opts["test"] = True
            assert_plan(
                cephfs_state.subvolume_group_present(
                    group,
                    filesystem,
                    size=64 * _MIB,
                    profile=_PROFILE,
                )
            )
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.subvolume_group_present(
                    group,
                    filesystem,
                    size=64 * _MIB,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.subvolume_group_present(
                    group,
                    filesystem,
                    size=64 * _MIB,
                    profile=_PROFILE,
                )
            )
            cephfs_opts["test"] = True
            update_plan = cephfs_state.subvolume_group_present(
                group,
                filesystem,
                size=96 * _MIB,
                profile=_PROFILE,
            )
            assert update_plan["result"] is None, update_plan["comment"]
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.subvolume_group_present(
                    group,
                    filesystem,
                    size=96 * _MIB,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.subvolume_group_present(
                    group,
                    filesystem,
                    size=96 * _MIB,
                    profile=_PROFILE,
                )
            )

            cephfs_opts["test"] = True
            assert_plan(
                cephfs_state.subvolume_present(
                    subvolume,
                    filesystem,
                    group_name=group,
                    size=16 * _MIB,
                    profile=_PROFILE,
                )
            )
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.subvolume_present(
                    subvolume,
                    filesystem,
                    group_name=group,
                    size=16 * _MIB,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.subvolume_present(
                    subvolume,
                    filesystem,
                    group_name=group,
                    size=16 * _MIB,
                    profile=_PROFILE,
                )
            )
            cephfs_opts["test"] = True
            update_plan = cephfs_state.subvolume_present(
                subvolume,
                filesystem,
                group_name=group,
                size=32 * _MIB,
                profile=_PROFILE,
            )
            assert update_plan["result"] is None, update_plan["comment"]
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.subvolume_present(
                    subvolume,
                    filesystem,
                    group_name=group,
                    size=32 * _MIB,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.subvolume_present(
                    subvolume,
                    filesystem,
                    group_name=group,
                    size=32 * _MIB,
                    profile=_PROFILE,
                )
            )

            cephfs_opts["test"] = True
            assert_plan(
                cephfs_state.subvolume_snapshot_present(
                    snapshot,
                    filesystem,
                    subvolume,
                    group_name=group,
                    profile=_PROFILE,
                )
            )
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.subvolume_snapshot_present(
                    snapshot,
                    filesystem,
                    subvolume,
                    group_name=group,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.subvolume_snapshot_present(
                    snapshot,
                    filesystem,
                    subvolume,
                    group_name=group,
                    profile=_PROFILE,
                )
            )

            cephfs_opts["test"] = True
            assert (
                cephfs_state.subvolume_snapshot_absent(
                    snapshot,
                    filesystem,
                    subvolume,
                    group_name=group,
                    profile=_PROFILE,
                )["result"]
                is None
            )
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.subvolume_snapshot_absent(
                    snapshot,
                    filesystem,
                    subvolume,
                    group_name=group,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.subvolume_snapshot_absent(
                    snapshot,
                    filesystem,
                    subvolume,
                    group_name=group,
                    profile=_PROFILE,
                )
            )

            cephfs_opts["test"] = True
            assert (
                cephfs_state.subvolume_absent(
                    subvolume,
                    filesystem,
                    group_name=group,
                    profile=_PROFILE,
                )["result"]
                is None
            )
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.subvolume_absent(
                    subvolume,
                    filesystem,
                    group_name=group,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.subvolume_absent(
                    subvolume,
                    filesystem,
                    group_name=group,
                    profile=_PROFILE,
                )
            )

            cephfs_opts["test"] = True
            assert (
                cephfs_state.subvolume_group_absent(
                    group,
                    filesystem,
                    profile=_PROFILE,
                )["result"]
                is None
            )
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.subvolume_group_absent(
                    group,
                    filesystem,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                cephfs_state.subvolume_group_absent(
                    group,
                    filesystem,
                    profile=_PROFILE,
                )
            )

            cephfs_opts["test"] = True
            assert cephfs_state.filesystem_absent(filesystem, profile=_PROFILE)["result"] is None
            cephfs_opts["test"] = False
            assert_changed(
                cephfs_state.filesystem_absent(
                    filesystem,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(cephfs_state.filesystem_absent(filesystem, profile=_PROFILE))
        finally:
            cephfs_opts["test"] = False
            pool_opts["test"] = False
            if _filesystem(live_client, filesystem) is not None:
                result = cephfs_state.filesystem_absent(
                    filesystem,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
                assert result["result"] is True, result["comment"]
            for name in (metadata_pool, data_pool):
                if _owned_pool(live_client, name) is not None:
                    result = pool_state.absent(
                        name,
                        confirm=True,
                        profile=_PROFILE,
                        task_interval=0.5,
                    )
                    assert result["result"] is True, result["comment"]


@pytest.mark.ceph_live_destructive
@pytest.mark.ceph_live_feature("orchestrator", "rgw")
def test_live_rgw_tenant_user_and_subuser_lifecycle(monkeypatch, live_client):
    """Reject unsupported tenant creation, then reconcile a user and subuser."""
    service_name = required_identity("CEPH_TEST_RGW_EXISTING_SERVICE")
    service_host = required_identity("CEPH_TEST_RGW_HOST")
    uid = required_identity("CEPH_TEST_RGW_USER")
    tenant_uid = required_identity("CEPH_TEST_RGW_TENANT_USER")
    subuser = required_identity("CEPH_TEST_RGW_SUBUSER")
    if tenant_uid.count("$") != 1:
        raise pytest.UsageError("CEPH_TEST_RGW_TENANT_USER must use tenant$user syntax.")
    if subuser != "saltext-ci-subuser":
        raise pytest.UsageError("CEPH_TEST_RGW_SUBUSER must be saltext-ci-subuser.")
    owner_marker = f"saltext-ci-owner:{uid}"
    resources = (f"service:{service_name}", f"host:{service_host}", f"rgw-user:{uid}")
    opts = bind_rgw_user_state(monkeypatch, live_client, test=True)

    if _service(live_client, service_name) is None:
        pytest.fail(f"required RGW service {service_name} is absent")
    daemon_name = _wait_for_rgw_ready(live_client, service_name, service_host)
    if _rgw_user(live_client, uid, daemon_name) is not None:
        pytest.fail(f"refusing to claim pre-existing RGW user {uid}")

    with live_client.infrastructure_lease(*resources):
        claimed = False
        confirmed_absent = False
        try:
            tenant_result = rgw_user_state.present(
                tenant_uid,
                f"saltext-ci-owner:{tenant_uid}",
                daemon_name=daemon_name,
                profile=_PROFILE,
            )
            assert tenant_result["result"] is False
            assert "cannot create tenant" in tenant_result["comment"]
            assert _rgw_user(live_client, tenant_uid, daemon_name) is None

            assert_plan(
                rgw_user_state.present(
                    uid,
                    owner_marker,
                    max_buckets=4,
                    system=False,
                    suspended=False,
                    generate_key=True,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )
            opts["test"] = False
            assert_changed(
                rgw_user_state.present(
                    uid,
                    owner_marker,
                    max_buckets=4,
                    system=False,
                    suspended=False,
                    generate_key=True,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            claimed = True
            assert_current(
                rgw_user_state.present(
                    uid,
                    owner_marker,
                    max_buckets=4,
                    system=False,
                    suspended=False,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )

            opts["test"] = True
            update_plan = rgw_user_state.present(
                uid,
                f"{owner_marker}:updated",
                max_buckets=8,
                system=False,
                suspended=False,
                daemon_name=daemon_name,
                profile=_PROFILE,
            )
            assert update_plan["result"] is None, update_plan["comment"]
            opts["test"] = False
            assert_changed(
                rgw_user_state.present(
                    uid,
                    f"{owner_marker}:updated",
                    max_buckets=8,
                    system=False,
                    suspended=False,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_user_state.present(
                    uid,
                    f"{owner_marker}:updated",
                    max_buckets=8,
                    system=False,
                    suspended=False,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )

            opts["test"] = True
            assert_plan(
                rgw_user_state.subuser_present(
                    subuser,
                    uid,
                    "read",
                    key_type="swift",
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )
            opts["test"] = False
            assert_changed(
                rgw_user_state.subuser_present(
                    subuser,
                    uid,
                    "read",
                    key_type="swift",
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_user_state.subuser_present(
                    subuser,
                    uid,
                    "read",
                    key_type="swift",
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )

            opts["test"] = True
            subuser_update_plan = rgw_user_state.subuser_present(
                subuser,
                uid,
                "readwrite",
                key_type="swift",
                daemon_name=daemon_name,
                profile=_PROFILE,
            )
            assert subuser_update_plan["result"] is None, subuser_update_plan["comment"]
            opts["test"] = False
            assert_changed(
                rgw_user_state.subuser_present(
                    subuser,
                    uid,
                    "readwrite",
                    key_type="swift",
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_user_state.subuser_present(
                    subuser,
                    uid,
                    "readwrite",
                    key_type="swift",
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )

            opts["test"] = True
            subuser_delete_plan = rgw_user_state.subuser_absent(
                subuser, uid, daemon_name=daemon_name, profile=_PROFILE
            )
            assert subuser_delete_plan["result"] is None, subuser_delete_plan["comment"]
            opts["test"] = False
            refused = rgw_user_state.subuser_absent(
                subuser, uid, daemon_name=daemon_name, profile=_PROFILE
            )
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert_changed(
                rgw_user_state.subuser_absent(
                    subuser,
                    uid,
                    daemon_name=daemon_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_user_state.subuser_absent(
                    subuser, uid, daemon_name=daemon_name, profile=_PROFILE
                )
            )

            opts["test"] = True
            user_delete_plan = rgw_user_state.absent(uid, daemon_name=daemon_name, profile=_PROFILE)
            assert user_delete_plan["result"] is None, user_delete_plan["comment"]
            opts["test"] = False
            refused = rgw_user_state.absent(uid, daemon_name=daemon_name, profile=_PROFILE)
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert_changed(
                rgw_user_state.absent(
                    uid,
                    daemon_name=daemon_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(rgw_user_state.absent(uid, daemon_name=daemon_name, profile=_PROFILE))
            confirmed_absent = True
        finally:
            opts["test"] = False
            if claimed and not confirmed_absent:
                if _owned_rgw_user(live_client, uid, owner_marker, daemon_name) is not None:
                    result = rgw_user_state.absent(
                        uid,
                        daemon_name=daemon_name,
                        confirm=True,
                        profile=_PROFILE,
                        task_interval=0.5,
                    )
                    assert result["result"] is True, result["comment"]


@pytest.mark.ceph_live_destructive
@pytest.mark.ceph_live_feature("orchestrator", "rgw")
def test_live_rgw_service_user_bucket_lifecycle(  # pylint: disable=too-many-statements
    monkeypatch, live_client
):
    """Reconcile a user, bucket, lifecycle, and policy on an existing RGW service."""
    service_name = required_identity("CEPH_TEST_RGW_EXISTING_SERVICE")
    service_host = required_identity("CEPH_TEST_RGW_HOST")
    uid = required_identity("CEPH_TEST_RGW_BUCKET_USER")
    bucket = required_identity("CEPH_TEST_RGW_BUCKET")
    if not service_name.startswith("rgw.saltext-ci-"):
        raise pytest.UsageError(
            "CEPH_TEST_RGW_SERVICE must use a unique rgw.saltext-ci-* service name."
        )
    owner_marker = f"saltext-ci-owner:{uid}"
    resources = (
        f"service:{service_name}",
        f"host:{service_host}",
        f"rgw-user:{uid}",
        f"bucket:{bucket}",
    )
    user_opts = bind_rgw_user_state(monkeypatch, live_client, test=True)
    bucket_opts = bind_rgw_bucket_state(monkeypatch, live_client, test=True)

    if _service(live_client, service_name) is None:
        pytest.fail(f"required RGW service {service_name} is absent")
    if _host(live_client, service_host) is None:
        pytest.fail(f"RGW placement host {service_host} is absent from the orchestrator")

    with live_client.infrastructure_lease(*resources):
        rgw_claims_proven = False
        daemon_name = None
        confirmed_absent = {"service"}
        try:
            _wait_for_running_service(live_client, service_name)
            daemon_name = _wait_for_rgw_ready(live_client, service_name, service_host)

            if _rgw_user(live_client, uid, daemon_name) is not None:
                pytest.fail(f"refusing to claim pre-existing RGW user {uid}")
            if _rgw_bucket(live_client, bucket, daemon_name) is not None:
                pytest.fail(f"refusing to claim pre-existing RGW bucket {bucket}")
            rgw_claims_proven = True

            assert_plan(
                rgw_user_state.present(
                    uid,
                    owner_marker,
                    max_buckets=4,
                    system=False,
                    suspended=False,
                    generate_key=True,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )
            user_opts["test"] = False
            assert_changed(
                rgw_user_state.present(
                    uid,
                    owner_marker,
                    max_buckets=4,
                    system=False,
                    suspended=False,
                    generate_key=True,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_user_state.present(
                    uid,
                    owner_marker,
                    max_buckets=4,
                    system=False,
                    suspended=False,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )

            user_opts["test"] = True
            update_plan = rgw_user_state.present(
                uid,
                f"{owner_marker}:updated",
                max_buckets=8,
                system=False,
                suspended=False,
                daemon_name=daemon_name,
                profile=_PROFILE,
            )
            assert update_plan["result"] is None, update_plan["comment"]
            user_opts["test"] = False
            assert_changed(
                rgw_user_state.present(
                    uid,
                    f"{owner_marker}:updated",
                    max_buckets=8,
                    system=False,
                    suspended=False,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_user_state.present(
                    uid,
                    f"{owner_marker}:updated",
                    max_buckets=8,
                    system=False,
                    suspended=False,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )

            assert_plan(
                rgw_bucket_state.present(
                    bucket,
                    uid,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )
            bucket_opts["test"] = False
            assert_changed(
                rgw_bucket_state.present(
                    bucket,
                    uid,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_bucket_state.present(
                    bucket,
                    uid,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )

            bucket_opts["test"] = True
            versioning_plan = rgw_bucket_state.versioning_present(
                bucket,
                "Enabled",
                daemon_name=daemon_name,
                profile=_PROFILE,
            )
            assert versioning_plan["result"] is None, versioning_plan["comment"]
            bucket_opts["test"] = False
            assert_changed(
                rgw_bucket_state.versioning_present(
                    bucket,
                    "Enabled",
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_bucket_state.versioning_present(
                    bucket,
                    "Enabled",
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )

            lifecycle = {
                "Rules": [
                    {
                        "ID": "saltext-ci-expire",
                        "Status": "Enabled",
                        "Prefix": "saltext-ci/",
                        "Expiration": {"Days": 30},
                    }
                ]
            }
            lifecycle_updated = {
                "Rules": [
                    {
                        "ID": "saltext-ci-expire",
                        "Status": "Enabled",
                        "Prefix": "saltext-ci/",
                        "Expiration": {"Days": 60},
                    }
                ]
            }
            bucket_opts["test"] = True
            lifecycle_plan = rgw_bucket_state.lifecycle_present(
                bucket,
                lifecycle,
                daemon_name=daemon_name,
                owner=uid,
                profile=_PROFILE,
            )
            assert lifecycle_plan["result"] is None, lifecycle_plan["comment"]
            bucket_opts["test"] = False
            lifecycle_result = rgw_bucket_state.lifecycle_present(
                bucket,
                lifecycle,
                daemon_name=daemon_name,
                owner=uid,
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert_changed(lifecycle_result)
            assert_current(
                rgw_bucket_state.lifecycle_present(
                    bucket,
                    lifecycle,
                    daemon_name=daemon_name,
                    owner=uid,
                    profile=_PROFILE,
                )
            )

            bucket_opts["test"] = True
            lifecycle_update_plan = rgw_bucket_state.lifecycle_present(
                bucket,
                lifecycle_updated,
                daemon_name=daemon_name,
                owner=uid,
                profile=_PROFILE,
            )
            assert lifecycle_update_plan["result"] is None, lifecycle_update_plan["comment"]
            bucket_opts["test"] = False
            assert_changed(
                rgw_bucket_state.lifecycle_present(
                    bucket,
                    lifecycle_updated,
                    daemon_name=daemon_name,
                    owner=uid,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_bucket_state.lifecycle_present(
                    bucket,
                    lifecycle_updated,
                    daemon_name=daemon_name,
                    owner=uid,
                    profile=_PROFILE,
                )
            )

            def transport_policy(sid):
                return {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": sid,
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:*",
                            "Resource": [
                                f"arn:aws:s3:::{bucket}",
                                f"arn:aws:s3:::{bucket}/*",
                            ],
                            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                        }
                    ],
                }

            policy = transport_policy("DenyInsecureTransport")
            policy_updated = transport_policy("DenyInsecureTransportUpdated")
            bucket_opts["test"] = True
            policy_plan = rgw_bucket_state.policy_present(
                bucket, policy, daemon_name=daemon_name, profile=_PROFILE
            )
            assert policy_plan["result"] is None, policy_plan["comment"]
            bucket_opts["test"] = False
            assert_changed(
                rgw_bucket_state.policy_present(
                    bucket,
                    policy,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_bucket_state.policy_present(
                    bucket, policy, daemon_name=daemon_name, profile=_PROFILE
                )
            )
            bucket_opts["test"] = True
            policy_update_plan = rgw_bucket_state.policy_present(
                bucket, policy_updated, daemon_name=daemon_name, profile=_PROFILE
            )
            assert policy_update_plan["result"] is None, policy_update_plan["comment"]
            bucket_opts["test"] = False
            assert_changed(
                rgw_bucket_state.policy_present(
                    bucket,
                    policy_updated,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_bucket_state.policy_present(
                    bucket, policy_updated, daemon_name=daemon_name, profile=_PROFILE
                )
            )

            bucket_opts["test"] = True
            lifecycle_delete_plan = rgw_bucket_state.lifecycle_absent(
                bucket, daemon_name=daemon_name, owner=uid, profile=_PROFILE
            )
            assert lifecycle_delete_plan["result"] is None, lifecycle_delete_plan["comment"]
            bucket_opts["test"] = False
            refused = rgw_bucket_state.lifecycle_absent(
                bucket, daemon_name=daemon_name, owner=uid, profile=_PROFILE
            )
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert_changed(
                rgw_bucket_state.lifecycle_absent(
                    bucket,
                    daemon_name=daemon_name,
                    owner=uid,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_bucket_state.lifecycle_absent(
                    bucket, daemon_name=daemon_name, owner=uid, profile=_PROFILE
                )
            )

            bucket_opts["test"] = True
            assert (
                rgw_bucket_state.absent(
                    bucket,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )["result"]
                is None
            )
            bucket_opts["test"] = False
            refused = rgw_bucket_state.absent(
                bucket,
                daemon_name=daemon_name,
                profile=_PROFILE,
            )
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert_changed(
                rgw_bucket_state.absent(
                    bucket,
                    daemon_name=daemon_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_bucket_state.absent(
                    bucket,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )
            confirmed_absent.add("bucket")

            user_opts["test"] = True
            assert (
                rgw_user_state.absent(
                    uid,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )["result"]
                is None
            )
            user_opts["test"] = False
            assert_changed(
                rgw_user_state.absent(
                    uid,
                    daemon_name=daemon_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                rgw_user_state.absent(
                    uid,
                    daemon_name=daemon_name,
                    profile=_PROFILE,
                )
            )
            confirmed_absent.add("user")

        finally:
            _, primary_error, primary_traceback = sys.exc_info()
            try:
                bucket_opts["test"] = False
                user_opts["test"] = False
                _cleanup_rgw_resources(
                    live_client,
                    _RgwLifecycleResources(
                        service_name=service_name,
                        service_host=service_host,
                        uid=uid,
                        owner_marker=owner_marker,
                        bucket=bucket,
                        daemon_name=daemon_name,
                    ),
                    rgw_claims_proven,
                    confirmed_absent,
                )
            except (
                Exception,
                pytest.fail.Exception,
            ) as cleanup_error:  # pylint: disable=broad-exception-caught
                if primary_error is None:
                    raise
                raise primary_error.with_traceback(primary_traceback) from cleanup_error
