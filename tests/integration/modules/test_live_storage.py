"""Read-only live tests for Ceph storage execution modules."""

from collections.abc import Mapping

import pytest

from saltext.ceph.utils.ceph import cephfs
from saltext.ceph.utils.ceph import crush_rule
from saltext.ceph.utils.ceph import erasure_code_profile
from saltext.ceph.utils.ceph import osd
from saltext.ceph.utils.ceph import pool
from saltext.ceph.utils.ceph import rbd

from ._live import load_execution_modules
from ._live import mapping_items
from ._live import response_data

pytestmark = pytest.mark.ceph_live


@pytest.fixture
def live_osds(live_client):
    return mapping_items(osd.list_(live_client))


@pytest.fixture
def live_pools(live_client):
    return mapping_items(pool.list_(live_client))


@pytest.fixture
def live_up_osd_id(live_osds):
    for item in live_osds:
        states = item.get("state")
        state_is_up = isinstance(states, list) and "up" in states
        if item.get("up") not in (True, 1) and not state_is_up:
            continue
        svc_id = item.get("id")
        if isinstance(svc_id, bool) or not isinstance(svc_id, int):
            pytest.fail("the OSD list returned an invalid numeric id for an up OSD")
        return svc_id
    pytest.skip("the cluster has no up OSDs")


def test_live_osd_collection_and_read_only_settings(live_client, live_osds):
    settings = response_data(osd.settings(live_client), Mapping)
    flags = response_data(osd.flags(live_client), list)
    individual_flags = mapping_items(osd.individual_flags(live_client))

    assert all(isinstance(item, Mapping) for item in live_osds)
    assert all(isinstance(name, str) for name in flags)
    assert isinstance(settings.get("nearfull_ratio"), (int, float))
    assert isinstance(settings.get("full_ratio"), (int, float))
    assert all(isinstance(item, Mapping) for item in individual_flags)


def test_live_up_osd_detail_contracts(live_client, live_up_osd_id):
    response_data(osd.get(live_client, live_up_osd_id), Mapping)
    mapping_items(osd.devices(live_client, live_up_osd_id))


@pytest.mark.parametrize("operation", (osd.smart, osd.histogram), ids=("smart", "histogram"))
def test_live_up_osd_telemetry(live_client, live_up_osd_id, operation):
    response_data(operation(live_client, live_up_osd_id), Mapping)


def test_live_pool_list_has_stable_identities(live_pools):
    names = [item.get("pool_name") for item in live_pools]
    assert all(isinstance(name, str) and name for name in names)
    assert len(names) == len(set(names))


def test_live_erasure_profiles_round_trip_by_name(live_client):
    profiles = mapping_items(erasure_code_profile.list_(live_client))
    if not profiles:
        pytest.skip("the cluster has no erasure-code profiles")
    name = profiles[0].get("name")
    if not isinstance(name, str) or not name:
        pytest.fail("the erasure-code profile list returned an invalid name")

    detail = response_data(erasure_code_profile.get(live_client, name), Mapping)
    assert detail.get("name") == name


def test_live_crush_rules_round_trip_by_name(live_client):
    rules = mapping_items(crush_rule.list_(live_client))
    if not rules:
        pytest.skip("the cluster has no CRUSH rules")
    name = rules[0].get("rule_name")
    if not isinstance(name, str) or not name:
        pytest.fail("the CRUSH rule list returned an invalid rule_name")

    detail = response_data(crush_rule.get(live_client, name), Mapping)
    assert detail.get("rule_name") == name


@pytest.mark.ceph_live_feature("cephfs")
def test_live_optional_cephfs_inventory(live_client):
    filesystems = response_data(cephfs.list_(live_client), list)
    assert all(isinstance(item, Mapping) for item in filesystems)


@pytest.mark.parametrize(
    "operation,expected_type",
    ((rbd.default_features, list), (rbd.clone_format_version, int)),
    ids=("default-features", "clone-format"),
)
@pytest.mark.ceph_live_feature("rbd")
def test_live_optional_rbd_defaults(live_client, operation, expected_type):
    response_data(operation(live_client), expected_type)


def test_salt_loader_executes_a_live_storage_module(live_client, monkeypatch, tmp_path):
    functions = load_execution_modules(tmp_path, monkeypatch, live_client)
    result = functions["ceph_osd.list"]()

    assert set(result) == {"status", "data", "headers"}
    assert 200 <= result["status"] < 300
    assert isinstance(result["data"], list)
