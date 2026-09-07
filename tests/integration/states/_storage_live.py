"""Bindings and assertions shared by destructive storage state tests.

The live tests call the real execution modules and state modules without
placing Dashboard credentials in Salt opts or pillar.  Only the client factory
is replaced, so request validation, response shaping, task waits, and state
reconciliation all remain in the exercised path.
"""

import os
import re

import pytest

from saltext.ceph.modules import ceph_pool as pool_execution
from saltext.ceph.modules import ceph_rbd as rbd_execution
from saltext.ceph.modules import ceph_rgw_bucket as rgw_bucket_execution
from saltext.ceph.modules import ceph_rgw_user as rgw_user_execution
from saltext.ceph.modules import ceph_service as service_execution
from saltext.ceph.modules import ceph_task as task_execution
from saltext.ceph.modules import cephfs as cephfs_execution
from saltext.ceph.states import ceph_pool as pool_state
from saltext.ceph.states import ceph_rbd as rbd_state
from saltext.ceph.states import ceph_rgw_bucket as rgw_bucket_state
from saltext.ceph.states import ceph_rgw_user as rgw_user_state
from saltext.ceph.states import ceph_service as service_state
from saltext.ceph.states import cephfs as cephfs_state
from saltext.ceph.utils import ceph as ceph_utils

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def required_identity(name):
    """Read one explicit, non-secret live resource identity.

    Destructive test identities deliberately have no defaults.  A caller that
    enabled the related live feature must state exactly which allowlisted name
    it expects this run to create and remove.
    """
    value = os.environ.get(name)
    if value is None:
        raise pytest.UsageError(f"{name} is required for this destructive live test.")
    if (
        not value
        or value != value.strip()
        or len(value) > 255
        or _CONTROL_RE.search(value)
        or any(char.isspace() for char in value)
    ):
        raise pytest.UsageError(f"{name} must contain one exact bounded resource identity.")
    return value


def configure_execution_modules(monkeypatch, live_client, *modules):
    """Inject normal Salt loader globals and route API calls to ``live_client``."""
    monkeypatch.setattr(
        ceph_utils,
        "get_client",
        lambda _opts, _pillar, _context, _profile="default": live_client,
    )
    for module in (task_execution, *modules):
        monkeypatch.setattr(module, "__opts__", {}, raising=False)
        monkeypatch.setattr(module, "__pillar__", {}, raising=False)
        monkeypatch.setattr(module, "__context__", {}, raising=False)
    return task_execution.wait


def bind_pool_state(monkeypatch, live_client, *, test):
    """Bind the pool state to the real pool and task execution functions."""
    waiter = configure_execution_modules(monkeypatch, live_client, pool_execution)
    opts = {"test": test}
    monkeypatch.setattr(pool_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        pool_state,
        "__salt__",
        {
            "ceph_pool.list": pool_execution.list_,
            "ceph_pool.get": pool_execution.get,
            "ceph_pool.create": pool_execution.create,
            "ceph_pool.update": pool_execution.update,
            "ceph_pool.delete": pool_execution.delete,
            "ceph_task.wait": waiter,
        },
        raising=False,
    )
    return opts


def bind_rbd_state(monkeypatch, live_client, *, test):
    """Bind image, namespace, and snapshot states to real execution functions."""
    waiter = configure_execution_modules(monkeypatch, live_client, rbd_execution)
    opts = {"test": test}
    monkeypatch.setattr(rbd_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        rbd_state,
        "__salt__",
        {
            "ceph_rbd.get": rbd_execution.get,
            "ceph_rbd.create": rbd_execution.create,
            "ceph_rbd.update": rbd_execution.update,
            "ceph_rbd.delete": rbd_execution.delete,
            "ceph_rbd.namespace_list": rbd_execution.namespace_list,
            "ceph_rbd.namespace_create": rbd_execution.namespace_create,
            "ceph_rbd.namespace_delete": rbd_execution.namespace_delete,
            "ceph_rbd.snapshot_create": rbd_execution.snapshot_create,
            "ceph_rbd.snapshot_update": rbd_execution.snapshot_update,
            "ceph_rbd.snapshot_delete": rbd_execution.snapshot_delete,
            "ceph_task.wait": waiter,
        },
        raising=False,
    )
    return opts


def bind_cephfs_state(monkeypatch, live_client, *, test):
    """Bind filesystem and subvolume states to their real execution surface."""
    waiter = configure_execution_modules(
        monkeypatch,
        live_client,
        cephfs_execution,
        service_execution,
    )
    opts = {"test": test}
    monkeypatch.setattr(cephfs_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        cephfs_state,
        "__salt__",
        {
            "cephfs.list": cephfs_execution.list_,
            "cephfs.create": cephfs_execution.create,
            "cephfs.remove": cephfs_execution.remove,
            "ceph_service.daemons": service_execution.daemons,
            "cephfs.group_list": cephfs_execution.group_list,
            "cephfs.group_create": cephfs_execution.group_create,
            "cephfs.group_resize": cephfs_execution.group_resize,
            "cephfs.group_remove": cephfs_execution.group_remove,
            "cephfs.subvolume_list": cephfs_execution.subvolume_list,
            "cephfs.subvolume_create": cephfs_execution.subvolume_create,
            "cephfs.subvolume_resize": cephfs_execution.subvolume_resize,
            "cephfs.subvolume_remove": cephfs_execution.subvolume_remove,
            "cephfs.subvolume_snapshot_list": cephfs_execution.subvolume_snapshot_list,
            "cephfs.subvolume_snapshot_create": cephfs_execution.subvolume_snapshot_create,
            "cephfs.subvolume_snapshot_remove": cephfs_execution.subvolume_snapshot_remove,
            "ceph_task.wait": waiter,
        },
        raising=False,
    )
    return opts


def bind_service_state(monkeypatch, live_client, *, test):
    """Bind the cephadm service state to real execution functions."""
    waiter = configure_execution_modules(monkeypatch, live_client, service_execution)
    opts = {"test": test}
    monkeypatch.setattr(service_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        service_state,
        "__salt__",
        {
            "ceph_service.list": service_execution.list_,
            "ceph_service.get": service_execution.get,
            "ceph_service.create": service_execution.create,
            "ceph_service.update": service_execution.update,
            "ceph_service.delete": service_execution.delete,
            "ceph_task.wait": waiter,
        },
        raising=False,
    )
    return opts


def bind_rgw_user_state(monkeypatch, live_client, *, test):
    """Bind the RGW user state to real execution functions."""
    waiter = configure_execution_modules(monkeypatch, live_client, rgw_user_execution)
    opts = {"test": test}
    monkeypatch.setattr(rgw_user_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        rgw_user_state,
        "__salt__",
        {
            "ceph_rgw_user.list_users": rgw_user_execution.list_users,
            "ceph_rgw_user.get_user": rgw_user_execution.get_user,
            "ceph_rgw_user.create_user": rgw_user_execution.create_user,
            "ceph_rgw_user.update_user": rgw_user_execution.update_user,
            "ceph_rgw_user.delete_user": rgw_user_execution.delete_user,
            "ceph_task.wait": waiter,
        },
        raising=False,
    )
    return opts


def bind_rgw_bucket_state(monkeypatch, live_client, *, test):
    """Bind the RGW bucket state to real execution functions."""
    waiter = configure_execution_modules(monkeypatch, live_client, rgw_bucket_execution)
    opts = {"test": test}
    monkeypatch.setattr(rgw_bucket_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        rgw_bucket_state,
        "__salt__",
        {
            "ceph_rgw_bucket.list_buckets": rgw_bucket_execution.list_buckets,
            "ceph_rgw_bucket.get_bucket": rgw_bucket_execution.get_bucket,
            "ceph_rgw_bucket.create_bucket": rgw_bucket_execution.create_bucket,
            "ceph_rgw_bucket.update_bucket": rgw_bucket_execution.update_bucket,
            "ceph_rgw_bucket.delete_bucket": rgw_bucket_execution.delete_bucket,
            "ceph_task.wait": waiter,
        },
        raising=False,
    )
    return opts


def assert_plan(result, *, old=None):
    """Assert Salt test mode returned a real diff rather than a success."""
    assert result["result"] is None, result["comment"]
    assert result["changes"]["old"] == old
    assert "new" in result["changes"]


def assert_changed(result):
    """Assert a mutation converged and reported both sides of its diff."""
    assert result["result"] is True, result["comment"]
    assert set(result["changes"]) == {"old", "new"}


def assert_current(result):
    """Assert a repeated declaration is idempotent."""
    assert result["result"] is True, result["comment"]
    assert result["changes"] == {}
