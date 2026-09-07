"""Tests for the destructive live storage request boundary."""

import json
from urllib.parse import quote

import pytest

from tests.integration._storage_policy import StoragePolicyError
from tests.integration._storage_policy import StorageWritePolicy
from tests.integration._storage_policy import validate_resource

POOL = "saltext-ci-pool"
NAMESPACE = "saltext-ci-namespace"
IMAGE = "saltext-ci-image"
RBD_SNAPSHOT = "saltext-ci-rbd-snapshot"
FS = "saltext-ci-fs"
DATA_POOL = "saltext-ci-data"
META_POOL = "saltext-ci-meta"
GROUP = "saltext-ci-group"
SUBVOLUME = "saltext-ci-subvolume"
FS_SNAPSHOT = "saltext-ci-fs-snapshot"
HOST = "ceph-01"
RGW_SERVICE = "rgw.saltext-ci-rgw"
RGW_DAEMON = "saltext-ci-rgw.ceph-01.test"
UID = "saltext-ci-user"
BUCKET = "saltext-ci-bucket"
IMAGE_SPEC = f"{POOL}/{IMAGE}"
SUBVOLUME_SPEC = f"{FS}/{GROUP}/{SUBVOLUME}"

LEASED = frozenset(
    (
        f"pool:{POOL}",
        f"pool:{DATA_POOL}",
        f"pool:{META_POOL}",
        f"namespace:{POOL}/{NAMESPACE}",
        f"image:{IMAGE_SPEC}",
        f"snapshot:{IMAGE_SPEC}@{RBD_SNAPSHOT}",
        f"fs:{FS}",
        f"host:{HOST}",
        f"service:{RGW_SERVICE}",
        f"cephfs-group:{FS}/{GROUP}",
        f"cephfs-subvolume:{SUBVOLUME_SPEC}",
        f"cephfs-snapshot:{SUBVOLUME_SPEC}@{FS_SNAPSHOT}",
        f"rgw-user:{UID}",
        f"bucket:{BUCKET}",
    )
)


@pytest.fixture
def policy():
    return StorageWritePolicy(LEASED)


@pytest.mark.parametrize(
    ("method", "path", "params", "data"),
    (
        (
            "POST",
            "/api/pool",
            None,
            {
                "pool": POOL,
                "pg_num": 8,
                "pool_type": "replicated",
                "application_metadata": ["rbd", "saltext_ci_owned"],
                "size": 3,
                "min_size": 2,
                "pg_autoscale_mode": "off",
            },
        ),
        (
            "PUT",
            f"/api/pool/{POOL}",
            None,
            {
                "application_metadata": [
                    "rbd",
                    "saltext_ci_owned",
                    "saltext_ci_updated",
                ]
            },
        ),
        ("PUT", f"/api/pool/{POOL}", None, {"pg_num": 8}),
        (
            "PUT",
            f"/api/pool/{DATA_POOL}",
            None,
            {
                "pg_num": 8,
                "size": 3,
                "min_size": 2,
                "pg_autoscale_mode": "off",
            },
        ),
        (
            "POST",
            "/api/pool",
            None,
            {
                "pool": DATA_POOL,
                "pg_num": 8,
                "pool_type": "replicated",
                "application_metadata": ["cephfs", "saltext_ci_owned"],
                "size": 3,
                "min_size": 2,
                "pg_autoscale_mode": "off",
            },
        ),
        ("DELETE", f"/api/pool/{POOL}", None, None),
        (
            "POST",
            f"/api/block/pool/{POOL}/namespace",
            None,
            {"namespace": NAMESPACE},
        ),
        (
            "DELETE",
            f"/api/block/pool/{POOL}/namespace/{NAMESPACE}",
            None,
            None,
        ),
        (
            "POST",
            "/api/block/image",
            None,
            {
                "name": IMAGE,
                "pool_name": POOL,
                "size": 8 * 1024 * 1024,
                "features": ["layering"],
                "metadata": {"saltext.ci.owner": f"saltext-ci-owner:{IMAGE}"},
            },
        ),
        (
            "PUT",
            f"/api/block/image/{quote(IMAGE_SPEC, safe='')}",
            None,
            {"metadata": {"saltext.ci.owner": f"saltext-ci-owner:{IMAGE}:updated"}},
        ),
        (
            "PUT",
            f"/api/block/image/{quote(IMAGE_SPEC, safe='')}",
            None,
            {"features": ["layering"]},
        ),
        ("DELETE", f"/api/block/image/{quote(IMAGE_SPEC, safe='')}", None, None),
        (
            "POST",
            f"/api/block/image/{quote(IMAGE_SPEC, safe='')}/snap",
            None,
            {"snapshot_name": RBD_SNAPSHOT, "mirrorImageSnapshot": False},
        ),
        (
            "DELETE",
            f"/api/block/image/{quote(IMAGE_SPEC, safe='')}/snap/{RBD_SNAPSHOT}",
            None,
            None,
        ),
        (
            "POST",
            "/api/cephfs",
            None,
            {
                "name": FS,
                "service_spec": {"placement": {"hosts": [HOST]}},
                "data_pool": DATA_POOL,
                "metadata_pool": META_POOL,
            },
        ),
        ("DELETE", f"/api/cephfs/remove/{FS}", None, None),
        (
            "POST",
            "/api/cephfs/subvolume/group",
            None,
            {"vol_name": FS, "group_name": GROUP, "size": 64 * 1024 * 1024},
        ),
        (
            "PUT",
            f"/api/cephfs/subvolume/group/{FS}",
            None,
            {"group_name": GROUP, "size": 96 * 1024 * 1024},
        ),
        (
            "DELETE",
            f"/api/cephfs/subvolume/group/{FS}",
            {"group_name": GROUP},
            None,
        ),
        (
            "POST",
            "/api/cephfs/subvolume",
            None,
            {
                "vol_name": FS,
                "subvol_name": SUBVOLUME,
                "group_name": GROUP,
                "size": 16 * 1024 * 1024,
            },
        ),
        (
            "PUT",
            f"/api/cephfs/subvolume/{FS}",
            None,
            {
                "subvol_name": SUBVOLUME,
                "group_name": GROUP,
                "size": 32 * 1024 * 1024,
            },
        ),
        (
            "DELETE",
            f"/api/cephfs/subvolume/{FS}",
            {
                "subvol_name": SUBVOLUME,
                "group_name": GROUP,
                "retain_snapshots": False,
            },
            None,
        ),
        (
            "POST",
            "/api/cephfs/subvolume/snapshot",
            None,
            {
                "vol_name": FS,
                "subvol_name": SUBVOLUME,
                "snap_name": FS_SNAPSHOT,
                "group_name": GROUP,
            },
        ),
        (
            "DELETE",
            f"/api/cephfs/subvolume/snapshot/{FS}/{SUBVOLUME}",
            {"snap_name": FS_SNAPSHOT, "group_name": GROUP, "force": True},
            None,
        ),
        (
            "POST",
            "/api/rgw/user",
            None,
            {
                "uid": UID,
                "display_name": f"saltext-ci-owner:{UID}",
                "max_buckets": 4,
                "system": False,
                "suspended": False,
                "generate_key": True,
                "daemon_name": RGW_DAEMON,
            },
        ),
        (
            "PUT",
            f"/api/rgw/user/{UID}",
            None,
            {
                "display_name": f"saltext-ci-owner:{UID}:updated",
                "max_buckets": 8,
                "system": False,
                "suspended": False,
                "daemon_name": RGW_DAEMON,
            },
        ),
        ("DELETE", f"/api/rgw/user/{UID}", {"daemon_name": RGW_DAEMON}, None),
        (
            "POST",
            "/api/rgw/bucket",
            None,
            {
                "bucket": BUCKET,
                "uid": UID,
                "lock_enabled": False,
                "encryption_state": False,
                "daemon_name": RGW_DAEMON,
            },
        ),
        (
            "PUT",
            f"/api/rgw/bucket/{BUCKET}",
            None,
            {
                "bucket_id": "test-generated-id",
                "uid": UID,
                "versioning_state": "Enabled",
                "encryption_state": False,
                "daemon_name": RGW_DAEMON,
            },
        ),
        ("DELETE", f"/api/rgw/bucket/{BUCKET}", {"daemon_name": RGW_DAEMON}, None),
    ),
)
def test_authorizes_exact_storage_lifecycle_requests(policy, method, path, params, data):
    assert policy.authorize(method, path, "1.0", params, data) is True


@pytest.mark.parametrize(
    ("kind", "identifier"),
    (
        ("pool", POOL),
        ("namespace", f"{POOL}/{NAMESPACE}"),
        ("image", IMAGE_SPEC),
        ("snapshot", f"{IMAGE_SPEC}@{RBD_SNAPSHOT}"),
        ("fs", FS),
        ("cephfs-group", f"{FS}/{GROUP}"),
        ("cephfs-subvolume", SUBVOLUME_SPEC),
        ("cephfs-snapshot", f"{SUBVOLUME_SPEC}@{FS_SNAPSHOT}"),
        ("rgw-user", UID),
        ("bucket", BUCKET),
    ),
)
def test_validates_canonical_storage_capabilities(kind, identifier):
    assert validate_resource(kind, identifier) == (kind, identifier)


@pytest.mark.parametrize(
    ("kind", "identifier"),
    (
        ("pool", "production"),
        ("namespace", f"{POOL}/production"),
        ("image", f"{POOL}/production"),
        ("snapshot", f"{IMAGE_SPEC}@production"),
        ("cephfs-group", f"{FS}/production"),
        ("cephfs-subvolume", f"{FS}/{GROUP}/production"),
        ("cephfs-snapshot", f"{SUBVOLUME_SPEC}@production"),
        ("unsupported", POOL),
    ),
)
def test_rejects_non_test_or_malformed_capabilities(kind, identifier):
    with pytest.raises(StoragePolicyError):
        validate_resource(kind, identifier)


def test_rejects_write_without_exact_resource_lease():
    policy = StorageWritePolicy((f"pool:{POOL}",))
    with pytest.raises(StoragePolicyError, match="exceeds"):
        policy.authorize(
            "POST",
            "/api/block/image",
            "1.0",
            None,
            {
                "name": IMAGE,
                "pool_name": POOL,
                "size": 8 * 1024 * 1024,
                "features": ["layering"],
                "metadata": {"saltext.ci.owner": f"saltext-ci-owner:{IMAGE}"},
            },
        )


@pytest.mark.parametrize(
    ("size", "min_size"),
    (
        (1, 1),
        (3, 1),
        (2, 2),
        (3, 3),
    ),
)
def test_pool_create_requires_the_exact_three_replica_baseline(policy, size, min_size):
    data = {
        "pool": POOL,
        "pg_num": 8,
        "pool_type": "replicated",
        "application_metadata": ["rbd", "saltext_ci_owned"],
        "size": size,
        "min_size": min_size,
        "pg_autoscale_mode": "off",
    }

    assert policy.authorize("POST", "/api/pool", "1.0", None, data) is False


@pytest.mark.parametrize(
    "data",
    (
        {},
        {"pg_num": 32},
        {"size": 2},
        {"min_size": 1},
        {"pg_autoscale_mode": "on"},
        {"quota_max_bytes": 1024},
        {"pg_num": 8, "quota_max_bytes": 1024},
        {"pg_num": 8, "application_metadata": ["rbd", "saltext_ci_owned"]},
    ),
)
def test_pool_corrective_update_rejects_unexpected_options(policy, data):
    assert policy.authorize("PUT", f"/api/pool/{POOL}", "1.0", None, data) is False


def test_pool_corrective_update_requires_test_prefix_even_when_leased():
    policy = StorageWritePolicy(("pool:production",))

    assert policy.authorize("PUT", "/api/pool/production", "1.0", None, {"pg_num": 8}) is False


def test_pool_corrective_update_requires_exact_pool_lease(policy):
    with pytest.raises(StoragePolicyError, match="exceeds"):
        policy.authorize("PUT", "/api/pool/saltext-ci-unleased", "1.0", None, {"pg_num": 8})


@pytest.mark.parametrize(
    "daemon_name",
    (
        "saltext-ci-rgw-other.ceph-01.test",
        "saltext-ci-rgw-extended.ceph-01.test",
        "rgw.saltext-ci-rgw-other.ceph-01.test",
        "../saltext-ci-rgw.ceph-01.test",
        "",
    ),
)
def test_rejects_daemon_outside_exact_leased_rgw_service(policy, daemon_name):
    data = {
        "uid": UID,
        "display_name": f"saltext-ci-owner:{UID}",
        "max_buckets": 4,
        "system": False,
        "suspended": False,
        "generate_key": True,
        "daemon_name": daemon_name,
    }

    assert policy.authorize("POST", "/api/rgw/user", "1.0", None, data) is False


def test_rejects_rgw_write_without_matching_service_lease():
    policy = StorageWritePolicy((f"rgw-user:{UID}",))
    data = {
        "uid": UID,
        "display_name": f"saltext-ci-owner:{UID}",
        "max_buckets": 4,
        "system": False,
        "suspended": False,
        "generate_key": True,
        "daemon_name": RGW_DAEMON,
    }

    assert policy.authorize("POST", "/api/rgw/user", "1.0", None, data) is False


def test_allows_subuser_lifecycle():
    encoded_uid = quote(UID, safe="")
    subuser_policy = StorageWritePolicy(LEASED)
    create_subuser = {
        "subuser": "saltext-ci-subuser",
        "access": "read",
        "key_type": "swift",
        "generate_secret": True,
        "daemon_name": RGW_DAEMON,
    }
    update_subuser = {
        **create_subuser,
        "subuser": f"{UID}:saltext-ci-subuser",
        "access": "readwrite",
        "generate_secret": False,
    }
    delete_subuser = {"purge_keys": True, "daemon_name": RGW_DAEMON}

    assert subuser_policy.authorize(
        "POST", f"/api/rgw/user/{encoded_uid}/subuser", "1.0", None, create_subuser
    )
    assert subuser_policy.authorize(
        "POST", f"/api/rgw/user/{encoded_uid}/subuser", "1.0", None, update_subuser
    )
    assert subuser_policy.authorize(
        "DELETE",
        f"/api/rgw/user/{encoded_uid}/subuser/{quote(f'{UID}:saltext-ci-subuser', safe='')}",
        "1.0",
        delete_subuser,
        None,
    )


def test_rejects_subuser_for_unleased_user():
    subuser_policy = StorageWritePolicy((f"service:{RGW_SERVICE}", f"rgw-user:{UID}"))
    data = {
        "subuser": "saltext-ci-subuser",
        "access": "read",
        "key_type": "swift",
        "generate_secret": True,
        "daemon_name": RGW_DAEMON,
    }

    assert (
        subuser_policy.authorize(
            "POST",
            "/api/rgw/user/saltext-ci-other/subuser",
            "1.0",
            None,
            data,
        )
        is False
    )


def test_allows_bounded_bucket_lifecycle_write(policy):
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
    data = {
        "bucket_name": BUCKET,
        "lifecycle": json.dumps(lifecycle),
        "daemon_name": RGW_DAEMON,
        "owner": UID,
    }

    assert policy.authorize("PUT", "/api/rgw/bucket/lifecycle", "1.0", None, data)


def test_allows_bounded_bucket_policy_write(policy):
    statement = {
        "Sid": "DenyInsecureTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"],
        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
    }
    data = {
        "bucket_id": "safe-bucket-id",
        "uid": UID,
        "encryption_state": False,
        "lifecycle": "{}",
        "bucket_policy": json.dumps({"Version": "2012-10-17", "Statement": [statement]}),
        "daemon_name": RGW_DAEMON,
    }

    assert policy.authorize("PUT", f"/api/rgw/bucket/{BUCKET}", "1.0", None, data)


@pytest.mark.parametrize(
    ("method", "path", "version", "params", "data"),
    (
        ("DELETE", f"/api/pool/{POOL}", "2.0", None, None),
        (
            "POST",
            "/api/pool",
            "1.0",
            None,
            {
                "pool": POOL,
                "pg_num": 8,
                "pool_type": "replicated",
                "application_metadata": ["rbd", "saltext_ci_owned"],
                "size": 3,
                "min_size": 1,
                "pg_autoscale_mode": "off",
            },
        ),
        (
            "PUT",
            f"/api/block/image/{quote(IMAGE_SPEC, safe='')}",
            "1.0",
            None,
            {"size": 1024},
        ),
        (
            "DELETE",
            f"/api/cephfs/subvolume/{FS}",
            "1.0",
            {"subvol_name": SUBVOLUME, "group_name": GROUP, "retain_snapshots": True},
            None,
        ),
        (
            "POST",
            "/api/rgw/user",
            "1.0",
            None,
            {
                "uid": UID,
                "display_name": f"saltext-ci-owner:{UID}",
                "max_buckets": 4,
                "system": True,
                "suspended": False,
                "generate_key": True,
                "daemon_name": RGW_DAEMON,
            },
        ),
    ),
)
def test_rejects_unsafe_storage_request_shapes(policy, method, path, version, params, data):
    assert policy.authorize(method, path, version, params, data) is False
