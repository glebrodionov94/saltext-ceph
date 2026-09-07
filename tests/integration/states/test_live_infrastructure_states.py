"""Opt-in host and service state lifecycles on a disposable Ceph cluster.

The exact host, address, service, and placement host come from non-secret
environment variables.  Every HTTP write remains inside a runtime lease whose
resource IDs must also occur verbatim in the destructive allowlist.
"""

import os
import re
import uuid
from collections.abc import Mapping

import pytest

from saltext.ceph.modules import ceph_host as host_execution
from saltext.ceph.modules import ceph_service as service_execution
from saltext.ceph.modules import ceph_task as task_execution
from saltext.ceph.states import ceph_host as host_state
from saltext.ceph.states import ceph_service as service_state
from saltext.ceph.utils.ceph import host as host_resource
from saltext.ceph.utils.ceph import host_api
from saltext.ceph.utils.ceph import service as service_resource
from saltext.ceph.utils.ceph import service_api
from saltext.ceph.utils.ceph import task as task_resource
from saltext.ceph.utils.ceph import task_api

pytestmark = pytest.mark.ceph_live

_PROFILE = "live"
_SAFE_VALUE = re.compile(r"[^\x00-\x20\x7f*?\[\]]+")


def _required_environment(name):
    value = os.environ.get(name)
    if value is None:
        pytest.skip(f"{name} is not configured for this live scenario")
    if not isinstance(value, str) or not _SAFE_VALUE.fullmatch(value):
        pytest.fail(f"{name} is not a bounded exact value", pytrace=False)
    return value


def _configure_execution_module(monkeypatch, module):
    monkeypatch.setattr(module, "__opts__", {}, raising=False)
    monkeypatch.setattr(module, "__pillar__", {}, raising=False)
    monkeypatch.setattr(module, "__context__", {}, raising=False)


def _bind_task_waiter(monkeypatch, live_client):
    _configure_execution_module(monkeypatch, task_execution)
    monkeypatch.setattr(task_api, "_client", lambda _opts, _pillar, _context, _profile: live_client)
    return task_execution.wait


def _bind_host_state(monkeypatch, live_client, *, test):
    _configure_execution_module(monkeypatch, host_execution)
    monkeypatch.setattr(host_api, "_client", lambda _opts, _pillar, _context, _profile: live_client)
    opts = {"test": test}
    monkeypatch.setattr(host_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        host_state,
        "__salt__",
        {
            "ceph_host.list": host_execution.list_,
            "ceph_host.create": host_execution.create,
            "ceph_host.delete": host_execution.delete,
            "ceph_host.drain": host_execution.drain,
            "ceph_host.set_labels": host_execution.set_labels,
            "ceph_host.toggle_maintenance": host_execution.toggle_maintenance,
            "ceph_task.wait": _bind_task_waiter(monkeypatch, live_client),
        },
        raising=False,
    )
    return opts


def _bind_service_state(monkeypatch, live_client, *, test):
    _configure_execution_module(monkeypatch, service_execution)
    monkeypatch.setattr(
        service_api,
        "_client",
        lambda _opts, _pillar, _context, _profile: live_client,
    )
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
            "ceph_task.wait": _bind_task_waiter(monkeypatch, live_client),
        },
        raising=False,
    )
    return opts


def _host_current(live_client, hostname):
    response = host_resource.list_(
        live_client,
        sources=["orchestrator"],
        facts=False,
        include_service_instances=False,
    )
    return next((item for item in response.data if item.get("hostname") == hostname), None)


def _service_current(live_client, service_name):
    response = service_resource.list_(live_client, service_name=service_name)
    if not any(item.get("service_name") == service_name for item in response.data):
        return None
    return service_resource.get(live_client, service_name).data


def _wait(live_client, response, timeout=1800.0):
    return task_resource.wait_response(live_client, response, timeout=timeout, interval=1.0)


def _cleanup_host(live_client, hostname, ownership_label):
    current = _host_current(live_client, hostname)
    if current is None:
        return
    labels = current.get("labels")
    if not isinstance(labels, list) or ownership_label not in labels:
        pytest.fail("refusing to remove a host without this test's ownership label")
    result = host_state.absent(
        hostname,
        confirm=True,
        drain=True,
        profile=_PROFILE,
        task_timeout=1800.0,
        task_interval=2.0,
    )
    assert result["result"] is True, result["comment"]
    assert _host_current(live_client, hostname) is None


def _cleanup_service(live_client, service_name, service_host):
    current = _service_current(live_client, service_name)
    if current is None:
        return
    placement = current.get("placement")
    if (
        not isinstance(placement, Mapping)
        or not isinstance(placement.get("hosts"), list)
        or service_host not in placement["hosts"]
    ):
        pytest.fail("refusing to remove a service without this test's exact placement host")
    _wait(live_client, service_resource.delete(live_client, service_name, confirm=True))
    assert _service_current(live_client, service_name) is None


@pytest.mark.ceph_live_feature("orchestrator")
@pytest.mark.ceph_live_destructive
def test_live_host_state_create_update_idempotency_and_delete(
    monkeypatch,
    live_settings,
    live_client,
):
    """Reconcile and remove one initially absent, exactly allowlisted host."""
    hostname = _required_environment("CEPH_TEST_INFRA_HOSTNAME")
    address = _required_environment("CEPH_TEST_INFRA_HOST_ADDRESS")
    resource = f"host:{hostname}"
    live_settings.require_destructive(resource)

    if _host_current(live_client, hostname) is not None:
        pytest.fail("configured lifecycle host already exists; refusing to claim or remove it")

    run_id = str(uuid.uuid4())
    owner = f"saltext-ci-owner-{run_id}"
    updated_label = "saltext-ci-updated"
    opts = _bind_host_state(monkeypatch, live_client, test=True)

    with live_client.infrastructure_lease(resource):
        try:
            plan = host_state.present(
                hostname,
                address=address,
                labels=[owner],
                maintenance=False,
                profile=_PROFILE,
            )
            assert plan["result"] is None
            assert plan["changes"]["old"] is None
            assert _host_current(live_client, hostname) is None

            opts["test"] = False
            created = host_state.present(
                hostname,
                address=address,
                labels=[owner],
                maintenance=False,
                profile=_PROFILE,
                task_interval=1.0,
            )
            assert created["result"] is True
            assert created["changes"]["old"] is None

            current = host_state.present(
                hostname,
                address=address,
                labels=[owner],
                maintenance=False,
                profile=_PROFILE,
            )
            assert current["result"] is True
            assert not current["changes"]

            opts["test"] = True
            update_plan = host_state.present(
                hostname,
                address=address,
                labels=[owner, updated_label],
                maintenance=False,
                profile=_PROFILE,
            )
            assert update_plan["result"] is None
            assert update_plan["changes"]["new"]["labels"] == sorted([owner, updated_label])

            opts["test"] = False
            updated = host_state.present(
                hostname,
                address=address,
                labels=[owner, updated_label],
                maintenance=False,
                profile=_PROFILE,
                task_interval=1.0,
            )
            assert updated["result"] is True
            assert updated["changes"]["new"]["labels"] == sorted([owner, updated_label])

            current = host_state.present(
                hostname,
                address=address,
                labels=[owner, updated_label],
                maintenance=False,
                profile=_PROFILE,
            )
            assert current["result"] is True
            assert not current["changes"]

            opts["test"] = True
            delete_plan = host_state.absent(hostname, profile=_PROFILE)
            assert delete_plan["result"] is None
            assert delete_plan["changes"]["new"] is None
            assert _host_current(live_client, hostname) is not None

            opts["test"] = False
            refused = host_state.absent(hostname, profile=_PROFILE)
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]

            deleted = host_state.absent(
                hostname,
                confirm=True,
                drain=True,
                profile=_PROFILE,
                task_interval=1.0,
            )
            assert deleted["result"] is True
            assert deleted["changes"]["new"] is None
            assert _host_current(live_client, hostname) is None
        finally:
            _cleanup_host(live_client, hostname, owner)


@pytest.mark.ceph_live_feature("orchestrator")
@pytest.mark.ceph_live_destructive
def test_live_service_state_create_update_idempotency_and_delete(
    monkeypatch,
    live_settings,
    live_client,
):
    """Reconcile one unique service from unmanaged to deployed, then remove it."""
    service_host = _required_environment("CEPH_TEST_INFRA_SERVICE_HOST")
    service_name = os.environ.get("CEPH_TEST_INFRA_SERVICE_NAME", "rgw.saltext-ci-live-rgw")
    if not _SAFE_VALUE.fullmatch(service_name):
        pytest.fail("CEPH_TEST_INFRA_SERVICE_NAME is not a bounded exact value", pytrace=False)
    resources = (f"service:{service_name}", f"host:{service_host}")
    live_settings.require_destructive(*resources)

    if _host_current(live_client, service_host) is None:
        pytest.fail("configured placement host is absent from the orchestrator")
    if _service_current(live_client, service_name) is not None:
        pytest.fail("configured lifecycle service already exists; refusing to claim or remove it")

    service_type, separator, service_id = service_name.partition(".")
    if not separator or service_type != "rgw" or not service_id.startswith("saltext-ci-"):
        pytest.fail("live service lifecycle requires a unique rgw.saltext-ci-* name", pytrace=False)
    base_spec = {
        "service_type": service_type,
        "service_id": service_id,
        "placement": {"hosts": [service_host]},
    }
    unmanaged_spec = {**base_spec, "unmanaged": True}
    deployed_spec = {**base_spec, "unmanaged": False}
    opts = _bind_service_state(monkeypatch, live_client, test=True)

    with live_client.infrastructure_lease(*resources):
        try:
            plan = service_state.present(service_name, unmanaged_spec, profile=_PROFILE)
            assert plan["result"] is None
            assert plan["changes"]["old"] is None
            assert _service_current(live_client, service_name) is None

            opts["test"] = False
            created = service_state.present(
                service_name,
                unmanaged_spec,
                profile=_PROFILE,
                task_interval=1.0,
            )
            assert created["result"] is True
            assert created["changes"]["old"] is None

            current = service_state.present(service_name, unmanaged_spec, profile=_PROFILE)
            assert current["result"] is True
            assert not current["changes"]

            opts["test"] = True
            update_plan = service_state.present(service_name, deployed_spec, profile=_PROFILE)
            assert update_plan["result"] is None
            assert update_plan["changes"]["new"]["unmanaged"] is False

            opts["test"] = False
            updated = service_state.present(
                service_name,
                deployed_spec,
                profile=_PROFILE,
                task_interval=1.0,
            )
            assert updated["result"] is True
            assert updated["changes"]["new"]["unmanaged"] is False

            current = service_state.present(service_name, deployed_spec, profile=_PROFILE)
            assert current["result"] is True
            assert not current["changes"]

            opts["test"] = True
            delete_plan = service_state.absent(service_name, profile=_PROFILE)
            assert delete_plan["result"] is None
            assert delete_plan["changes"]["new"] is None

            opts["test"] = False
            refused = service_state.absent(service_name, profile=_PROFILE)
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]

            deleted = service_state.absent(
                service_name,
                confirm=True,
                profile=_PROFILE,
                task_interval=1.0,
            )
            assert deleted["result"] is True
            assert deleted["changes"]["new"] is None
            assert _service_current(live_client, service_name) is None
        finally:
            _cleanup_service(live_client, service_name, service_host)
