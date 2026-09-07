"""Read-only live tests for cephadm inventory execution modules."""

from collections.abc import Mapping

import pytest

from saltext.ceph.utils.ceph import cluster
from saltext.ceph.utils.ceph import daemon
from saltext.ceph.utils.ceph import hardware
from saltext.ceph.utils.ceph import host
from saltext.ceph.utils.ceph import service

from ._live import load_execution_modules
from ._live import mapping_items
from ._live import response_data

pytestmark = pytest.mark.ceph_live


@pytest.fixture
def live_hosts(live_client):
    return mapping_items(host.list_(live_client, sources=["orchestrator"]))


@pytest.fixture
def live_services(live_client):
    return mapping_items(service.list_(live_client))


@pytest.fixture
def live_daemons(live_client):
    return mapping_items(daemon.list_(live_client))


@pytest.mark.ceph_live_feature("orchestrator")
def test_live_host_inventory_has_stable_identities(live_hosts):
    hostnames = [item.get("hostname") for item in live_hosts]
    assert all(isinstance(hostname, str) and hostname for hostname in hostnames)
    assert len(hostnames) == len(set(hostnames))


@pytest.mark.ceph_live_feature("orchestrator")
def test_live_first_host_read_subresources(live_client, live_hosts):
    if not live_hosts:
        pytest.skip("the orchestrator has no hosts")
    hostname = live_hosts[0]["hostname"]

    detail = response_data(host.get(live_client, hostname), Mapping)
    inventory = response_data(host.inventory(live_client, hostname), Mapping)
    devices = mapping_items(host.devices(live_client, hostname))
    daemons = mapping_items(host.daemons(live_client, hostname))
    smart = response_data(host.smart(live_client, hostname), Mapping)

    assert detail.get("hostname") == hostname
    assert inventory.get("name") in (None, hostname)
    assert all(isinstance(item, Mapping) for item in devices)
    assert all(item.get("hostname") in (None, hostname) for item in daemons)
    assert isinstance(smart, Mapping)


@pytest.mark.ceph_live_feature("orchestrator")
def test_live_service_types_cover_reported_services(live_client, live_services):
    known_types = response_data(service.known_types(live_client), list)
    assert all(isinstance(name, str) and name for name in known_types)
    assert len(known_types) == len(set(known_types))
    assert all(item.get("service_type") in known_types for item in live_services)


@pytest.mark.ceph_live_feature("orchestrator")
def test_live_first_service_and_its_daemons(live_client, live_services):
    if not live_services:
        pytest.skip("the orchestrator has no services")
    service_name = live_services[0].get("service_name")
    if not isinstance(service_name, str) or not service_name:
        pytest.fail("the service list returned an invalid service_name")

    detail = response_data(service.get(live_client, service_name), Mapping)
    members = mapping_items(service.daemons(live_client, service_name))

    assert detail.get("service_name") == service_name
    assert all(isinstance(item.get("daemon_name"), str) for item in members)


@pytest.mark.ceph_live_feature("orchestrator")
def test_live_daemon_filter_preserves_requested_type(live_client, live_daemons):
    if not live_daemons:
        pytest.skip("the orchestrator has no daemons")
    daemon_type = live_daemons[0].get("daemon_type")
    if not isinstance(daemon_type, str) or not daemon_type:
        pytest.fail("the daemon list returned an invalid daemon_type")

    filtered = mapping_items(daemon.list_(live_client, [daemon_type]))
    assert all(item.get("daemon_type") == daemon_type for item in filtered)


def test_live_cluster_status(live_client):
    cluster_status = response_data(cluster.status(live_client), Mapping)

    assert cluster_status.get("status") in cluster.CLUSTER_STATUSES


@pytest.mark.ceph_live_feature("orchestrator")
def test_live_upgrade_status(live_client):
    upgrade_status = response_data(cluster.upgrade_status(live_client), Mapping)

    assert isinstance(upgrade_status, Mapping)


@pytest.mark.ceph_live_feature("orchestrator", "hardware")
def test_live_current_hardware_status(live_client):
    hardware_status = response_data(hardware.summary(live_client), Mapping)

    assert isinstance(hardware_status, Mapping)


@pytest.mark.ceph_live_feature("orchestrator")
def test_salt_loader_executes_a_live_cephadm_module(live_client, monkeypatch, tmp_path):
    functions = load_execution_modules(tmp_path, monkeypatch, live_client)
    result = functions["ceph_host.list"]()

    assert set(result) == {"status", "data", "headers"}
    assert 200 <= result["status"] < 300
    assert isinstance(result["data"], list)
