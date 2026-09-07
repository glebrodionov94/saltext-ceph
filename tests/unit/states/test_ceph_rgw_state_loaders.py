"""Verify public RGW states through Salt's real state loader."""

from unittest.mock import Mock

import pytest
import salt.loader

from saltext.ceph.states import ceph_rgw_bucket
from saltext.ceph.states import ceph_rgw_iam
from saltext.ceph.states import ceph_rgw_multisite
from saltext.ceph.states import ceph_rgw_topic
from saltext.ceph.states import ceph_rgw_user


@pytest.mark.parametrize(
    ("module", "virtual_name", "names"),
    (
        (
            ceph_rgw_user,
            "ceph_rgw_user",
            (
                "present",
                "absent",
                "subuser_present",
                "subuser_absent",
                "capability_present",
                "capability_absent",
                "quota_present",
                "rate_limit_present",
                "managed_policies_present",
            ),
        ),
        (
            ceph_rgw_bucket,
            "ceph_rgw_bucket",
            (
                "present",
                "absent",
                "versioning_present",
                "encryption_present",
                "encryption_absent",
                "lifecycle_present",
                "lifecycle_absent",
                "notifications_present",
                "notifications_absent",
                "policy_present",
                "replication_present",
                "rate_limit_present",
            ),
        ),
        (
            ceph_rgw_multisite,
            "ceph_rgw_multisite",
            (
                "realm_present",
                "realm_absent",
                "zonegroup_present",
                "zonegroup_absent",
                "zone_present",
                "zone_absent",
                "placement_present",
                "storage_class_present",
                "storage_class_absent",
                "sync_group_present",
                "sync_group_absent",
                "sync_flow_present",
                "sync_flow_absent",
                "sync_pipe_present",
                "sync_pipe_absent",
            ),
        ),
        (ceph_rgw_topic, "ceph_rgw_topic", ("present", "absent")),
        (
            ceph_rgw_iam,
            "ceph_rgw_iam",
            (
                "account_present",
                "account_absent",
                "account_quota_present",
                "role_present",
                "role_absent",
            ),
        ),
    ),
)
def test_real_salt_loader_resolves_rgw_states(
    minion_opts, monkeypatch, module, virtual_name, names
):
    monkeypatch.setattr(module, "__salt__", {}, raising=False)
    missing = module.__virtual__()[1].removeprefix("Missing execution functions: ")
    functions = {name: Mock() for name in missing.split(", ")}
    loader = salt.loader.states(
        minion_opts,
        functions,
        salt.loader.utils(minion_opts),
        salt.loader.serializers(minion_opts),
        whitelist=[virtual_name],
    )
    assert all(callable(loader[f"{virtual_name}.{name}"]) for name in names)
