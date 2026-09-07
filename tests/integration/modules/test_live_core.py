"""Read-only live tests for core Ceph Dashboard execution modules."""

import uuid
from collections.abc import Mapping

import pytest

from saltext.ceph.utils.ceph import health
from saltext.ceph.utils.ceph import monitor
from saltext.ceph.utils.ceph import summary

from ._live import load_execution_modules
from ._live import response_data

pytestmark = pytest.mark.ceph_live


@pytest.mark.parametrize(
    "operation",
    (health.minimal, health.full, health.capacity),
    ids=("minimal", "full", "capacity"),
)
def test_live_health_mapping_contracts(live_client, operation):
    data = response_data(operation(live_client), Mapping)
    assert data


@pytest.mark.ceph_live_feature("health_snapshot")
def test_live_current_health_snapshot_mapping_contract(live_client):
    data = response_data(health.snapshot(live_client), Mapping)
    assert data


def test_live_fsid_is_a_uuid_and_matches_the_guard(live_client, live_settings):
    actual = str(uuid.UUID(response_data(health.fsid(live_client), str)))
    expected = getattr(live_settings, "expected_fsid", None)
    if expected is not None:
        assert actual == str(uuid.UUID(expected))


def test_live_health_scalar_contracts(live_client):
    enabled = response_data(health.telemetry_enabled(live_client), bool)
    assert enabled in (True, False)


def test_live_summary_has_task_and_health_contracts(live_client):
    data = response_data(summary.get(live_client), Mapping)
    assert isinstance(data.get("health_status"), str)
    assert isinstance(data.get("executing_tasks"), list)
    assert isinstance(data.get("finished_tasks"), list)


def test_live_monitor_quorum_contract(live_client):
    data = response_data(monitor.status(live_client), Mapping)
    assert isinstance(data.get("mon_status"), Mapping)
    assert isinstance(data.get("in_quorum"), list)
    assert isinstance(data.get("out_quorum"), list)

    def identities(entries):
        result = []
        for entry in entries:
            identity = entry.get("name") if isinstance(entry, Mapping) else entry
            assert isinstance(identity, str) and identity
            result.append(identity)
        return result

    assert set(identities(data["in_quorum"])).isdisjoint(identities(data["out_quorum"]))


def test_salt_loader_executes_a_live_core_module(live_client, monkeypatch, tmp_path):
    functions = load_execution_modules(tmp_path, monkeypatch, live_client)
    result = functions["ceph_health.fsid"]()

    assert set(result) == {"status", "data", "headers"}
    assert 200 <= result["status"] < 300
    uuid.UUID(result["data"])
