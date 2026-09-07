"""Destructive opt-in lifecycle for one exact cephadm-managed OSD.

The exact host, device path, and OSD service identity are supplied explicitly,
and every write passes through a runtime infrastructure lease.  The numeric
OSD ID is not trusted from configuration: it is claimed only after fresh host
inventory ties the newly created LVM to the exact drive-group service, host,
path, and stable device ID.

Ceph Dashboard 20.2 does not expose cephadm's device-zap operation.  Removing
the OSD therefore removes its cluster identity but can leave VG/LV metadata on
the disk.  The service spec is made unmanaged before removal and deleted only
after the OSD is gone, preventing automatic redeployment on that device.
"""

import time
from collections.abc import Mapping

import pytest
from salt.exceptions import SaltInvocationError

from saltext.ceph.modules import ceph_osd as osd_execution
from saltext.ceph.states import ceph_osd as osd_state
from saltext.ceph.states import ceph_service as service_state
from saltext.ceph.utils.ceph import host as host_resource
from saltext.ceph.utils.ceph import osd as osd_resource
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import service as service_resource

from ._storage_live import assert_changed
from ._storage_live import assert_current
from ._storage_live import bind_service_state
from ._storage_live import configure_execution_modules
from ._storage_live import required_identity

pytestmark = pytest.mark.ceph_live

_PROFILE = "live"
_DEVICE_CLASS = "saltext_ci"
_MINIMUM_BASELINE_OSDS = 3
_CLEANUP_RETRY_TIMEOUT = 60.0
_CLEANUP_RETRY_INTERVAL = 2.0
_TRANSIENT_CLEANUP_MARKERS = (
    "Ceph API HTTP 408:",
    "Ceph API HTTP 429:",
    "Ceph API HTTP 500:",
    "Ceph API HTTP 502:",
    "Ceph API HTTP 503:",
    "Ceph API HTTP 504:",
    "Ceph API request timed out;",
    "Ceph API connection failed;",
    "Ceph API returned a non-JSON response.",
    "Ceph API returned invalid JSON.",
    "Ceph OSD list returned an invalid Salt envelope.",
    "Ceph OSD list returned an unexpected response shape.",
    "Last post-mutation read reported ",
)


def _bind_osd_state(monkeypatch, live_client, *, test):
    """Bind the OSD state to real execution functions and the guarded client."""
    waiter = configure_execution_modules(monkeypatch, live_client, osd_execution)
    opts = {"test": test}
    monkeypatch.setattr(osd_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        osd_state,
        "__salt__",
        {
            "ceph_osd.list": osd_execution.list_,
            "ceph_osd.set_device_class": osd_execution.set_device_class,
            "ceph_osd.safe_to_delete": osd_execution.safe_to_delete,
            "ceph_osd.remove": osd_execution.remove,
            "ceph_task.wait": waiter,
        },
        raising=False,
    )
    return opts, waiter


def _inventory(live_client, hostname):
    current = host_resource.inventory(live_client, hostname, refresh=True).data
    if not isinstance(current, Mapping) or current.get("name", current.get("hostname")) != hostname:
        pytest.fail("host inventory did not match the exact OSD placement host")
    if not isinstance(current.get("devices"), list):
        pytest.fail("host inventory did not contain a device list")
    return current


def _require_registered_host(live_client, hostname):
    """Gate independently on a host already reconciled into cephadm."""
    items = host_resource.list_(
        live_client,
        sources=["orchestrator"],
        facts=False,
        include_service_instances=False,
    ).data
    matches = [
        item for item in items if isinstance(item, Mapping) and item.get("hostname") == hostname
    ]
    if not matches:
        pytest.skip(
            f"OSD lifecycle requires {hostname} to be added first "
            "(for example with ceph_host.present)"
        )
    if len(matches) != 1:
        pytest.fail(f"orchestrator returned duplicate host identity {hostname}")


def _target_device(inventory, device_path):
    matches = [
        item
        for item in inventory["devices"]
        if isinstance(item, Mapping) and item.get("path") == device_path
    ]
    if len(matches) != 1:
        pytest.fail(f"host inventory must contain exactly one {device_path} record")
    return matches[0]


def _available_device_inventory(live_client, hostname, device_path):
    inventory = _inventory(live_client, hostname)
    device = _target_device(inventory, device_path)
    if (
        device.get("available") is not True
        or device.get("osd_ids") != []
        or device.get("rejected_reasons", []) != []
        or device.get("lvs", []) != []
    ):
        pytest.fail(
            f"refusing to claim {hostname}:{device_path}: the device is not empty and available"
        )
    device_id = device.get("device_id")
    if device_id not in (None, "") and not isinstance(device_id, str):
        pytest.fail("host inventory returned an invalid stable device identity")
    return inventory, device_id or None


def _service(live_client, service_name):
    matches = [
        item
        for item in service_resource.list_(live_client, service_name=service_name).data
        if item.get("service_name") == service_name
    ]
    if len(matches) > 1:
        pytest.fail(f"service inventory returned duplicate identity {service_name}")
    return matches[0] if matches else None


def _owned_osd_service(live_client, service_name, service_id, hostname, device_path):
    if _service(live_client, service_name) is None:
        return None
    current = service_resource.get(live_client, service_name).data
    nested_spec = current.get("spec")
    if nested_spec is not None and not isinstance(nested_spec, Mapping):
        pytest.fail("OSD service returned a non-mapping nested spec")
    projected = {**current, **(nested_spec or {})}
    placement = projected.get("placement")
    devices = projected.get("data_devices")
    if (
        current.get("service_name") != service_name
        or projected.get("service_type") != "osd"
        or projected.get("service_id") != service_id
        or not isinstance(placement, Mapping)
        or placement.get("hosts") != [hostname]
        or not isinstance(devices, Mapping)
        or devices.get("paths") != [device_path]
    ):
        pytest.fail("refusing to mutate an OSD service without exact host/device ownership")
    return current


def _osds(live_client):
    items = osd_resource.list_(live_client, limit=-1).data
    result = {}
    for item in items:
        if not isinstance(item, Mapping):
            pytest.fail("OSD inventory returned a non-mapping entry")
        svc_id = item.get("id", item.get("osd"))
        if isinstance(svc_id, bool) or not isinstance(svc_id, int) or svc_id < 0:
            pytest.fail("OSD inventory returned a non-canonical identifier")
        if svc_id in result:
            pytest.fail(f"OSD inventory returned duplicate identity {svc_id}")
        result[svc_id] = item
    return result


def _has_osd_state(item, state):
    states = item.get("state")
    return item.get(state) in (True, 1) or (isinstance(states, list) and state in states)


def _require_safe_baseline(live_client):
    items = _osds(live_client)
    ready = {
        svc_id
        for svc_id, item in items.items()
        if _has_osd_state(item, "up") and _has_osd_state(item, "in")
    }
    if len(ready) < _MINIMUM_BASELINE_OSDS:
        pytest.skip(
            "OSD lifecycle requires at least three pre-existing up/in OSDs "
            "so the exact test OSD can be drained safely"
        )
    return frozenset(items)


def _wait_for_service(
    live_client,
    service_name,
    service_id,
    hostname,
    device_path,
    timeout=300.0,
):
    deadline = time.monotonic() + timeout
    while True:
        current = _service(live_client, service_name)
        if current is not None:
            return _owned_osd_service(
                live_client,
                service_name,
                service_id,
                hostname,
                device_path,
            )
        if time.monotonic() >= deadline:
            pytest.fail(f"OSD service {service_name} did not appear before timeout")
        time.sleep(2.0)


def _wait_for_claim_inventory(live_client, hostname, device_path, timeout=1800.0):
    deadline = time.monotonic() + timeout
    while True:
        inventory = _inventory(live_client, hostname)
        device = _target_device(inventory, device_path)
        osd_ids = device.get("osd_ids")
        lvs = device.get("lvs")
        if isinstance(osd_ids, list) and len(osd_ids) == 1 and isinstance(lvs, list) and lvs:
            return inventory
        if time.monotonic() >= deadline:
            pytest.fail("the exact test device did not expose one created OSD before timeout")
        time.sleep(5.0)


def _wait_for_osd(live_client, svc_id, timeout=600.0):
    deadline = time.monotonic() + timeout
    while True:
        current = _osds(live_client).get(svc_id)
        if current is not None and _has_osd_state(current, "up"):
            return current
        if time.monotonic() >= deadline:
            pytest.fail(f"OSD {svc_id} did not become up before timeout")
        time.sleep(2.0)


def _unmanaged_spec(spec):
    return {**spec, "unmanaged": True}


def _disable_redeployment(
    live_client,
    service_name,
    service_id,
    hostname,
    device_path,
    spec,
    service_opts,
):
    if _owned_osd_service(live_client, service_name, service_id, hostname, device_path) is None:
        return
    service_opts["test"] = False
    result = service_state.present(
        service_name,
        _unmanaged_spec(spec),
        profile=_PROFILE,
        task_interval=0.5,
    )
    assert result["result"] is True, result["comment"]


def _is_transient_cleanup_failure(result):
    """Recognize sanitized Dashboard read failures that are safe to retry."""
    if not isinstance(result, Mapping) or result.get("result") is not False:
        return False
    comment = result.get("comment")
    return isinstance(comment, str) and any(
        marker in comment for marker in _TRANSIENT_CLEANUP_MARKERS
    )


def _cleanup_osd_absence(
    svc_id,
    *,
    retry_timeout=_CLEANUP_RETRY_TIMEOUT,
    retry_interval=_CLEANUP_RETRY_INTERVAL,
):
    """Confirm absence through the state, retrying only transient read failures."""
    deadline = time.monotonic() + retry_timeout
    while True:
        result = osd_state.absent(
            svc_id,
            confirm=True,
            preserve_id=False,
            force=False,
            profile=_PROFILE,
            task_timeout=7200.0,
            task_interval=5.0,
        )
        if isinstance(result, Mapping) and result.get("result") is True:
            return result
        if not _is_transient_cleanup_failure(result):
            comment = result.get("comment") if isinstance(result, Mapping) else None
            pytest.fail(
                comment or "OSD cleanup state returned an invalid failure result", pytrace=False
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail(
                f"OSD {svc_id} absence was not confirmed before the cleanup retry deadline: "
                f"{result['comment']}",
                pytrace=False,
            )
        time.sleep(min(retry_interval, remaining))


@pytest.mark.ceph_live_destructive
@pytest.mark.ceph_live_feature("orchestrator")
def test_live_osd_drive_group_device_class_and_removal_lifecycle(monkeypatch, live_client):
    """Create one exact OSD, reconcile its class, then remove its API resources."""
    service_name = required_identity("CEPH_TEST_OSD_SERVICE")
    hostname = required_identity("CEPH_TEST_OSD_HOST")
    device_path = required_identity("CEPH_TEST_OSD_DEVICE")
    if not service_name.startswith("osd.saltext-ci-") or service_name.count(".") != 1:
        raise pytest.UsageError(
            "CEPH_TEST_OSD_SERVICE must be one unique osd.saltext-ci-* service name."
        )
    if not device_path.startswith("/dev/"):
        raise pytest.UsageError("CEPH_TEST_OSD_DEVICE must be one exact /dev path.")
    service_id = service_name.split(".", 1)[1]
    _require_registered_host(live_client, hostname)
    initial_osds = _require_safe_baseline(live_client)
    if _service(live_client, service_name) is not None:
        pytest.fail(f"refusing to claim pre-existing OSD service {service_name}")
    device_inventory, device_id = _available_device_inventory(
        live_client,
        hostname,
        device_path,
    )

    resources = [
        f"service:{service_name}",
        f"host:{hostname}",
        f"device:{hostname}:{device_path}",
    ]
    if device_id is not None:
        resources.append(f"device-id:{hostname}:{device_id}")

    spec = {
        "service_type": "osd",
        "service_id": service_id,
        "placement": {"hosts": [hostname]},
        "data_devices": {"paths": [device_path]},
        "encrypted": False,
    }
    osd_opts, waiter = _bind_osd_state(monkeypatch, live_client, test=True)
    service_opts = bind_service_state(monkeypatch, live_client, test=False)
    claimed_id = None
    create_submitted = False

    with live_client.infrastructure_lease(*resources, device_inventory=device_inventory):
        try:
            with pytest.raises(SaltInvocationError, match="confirm=True"):
                osd_execution.create(
                    "drive_groups",
                    [spec],
                    service_name,
                    confirm=False,
                    profile=_PROFILE,
                )

            response = osd_execution.create(
                "drive_groups",
                [spec],
                service_name,
                confirm=True,
                profile=_PROFILE,
            )
            create_submitted = True
            reconcile.wait_if_accepted(
                {"ceph_task.wait": waiter},
                response,
                profile=_PROFILE,
                timeout=1800.0,
                interval=2.0,
            )

            post_inventory = _wait_for_claim_inventory(live_client, hostname, device_path)
            claimed = live_client.claim_created_osds(post_inventory)
            assert len(claimed) == 1
            claimed_id = claimed[0]
            if claimed_id in initial_osds:
                pytest.fail("fresh device provenance resolved to a pre-existing OSD ID")
            _wait_for_osd(live_client, claimed_id)
            _wait_for_service(
                live_client,
                service_name,
                service_id,
                hostname,
                device_path,
            )

            assert_current(
                service_state.present(
                    service_name,
                    spec,
                    profile=_PROFILE,
                )
            )

            class_plan = osd_state.device_class_managed(
                claimed_id,
                _DEVICE_CLASS,
                profile=_PROFILE,
            )
            assert class_plan["result"] is None, class_plan["comment"]
            osd_opts["test"] = False
            assert_changed(
                osd_state.device_class_managed(
                    claimed_id,
                    _DEVICE_CLASS,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                osd_state.device_class_managed(
                    claimed_id,
                    _DEVICE_CLASS,
                    profile=_PROFILE,
                )
            )

            service_opts["test"] = True
            unmanaged_plan = service_state.present(
                service_name,
                _unmanaged_spec(spec),
                profile=_PROFILE,
            )
            assert unmanaged_plan["result"] is None, unmanaged_plan["comment"]
            service_opts["test"] = False
            assert_changed(
                service_state.present(
                    service_name,
                    _unmanaged_spec(spec),
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(
                service_state.present(
                    service_name,
                    _unmanaged_spec(spec),
                    profile=_PROFILE,
                )
            )

            osd_opts["test"] = True
            remove_plan = osd_state.absent(claimed_id, profile=_PROFILE)
            assert remove_plan["result"] is None, remove_plan["comment"]
            osd_opts["test"] = False
            refused = osd_state.absent(claimed_id, profile=_PROFILE)
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert_changed(
                osd_state.absent(
                    claimed_id,
                    confirm=True,
                    preserve_id=False,
                    force=False,
                    profile=_PROFILE,
                    task_timeout=7200.0,
                    task_interval=5.0,
                )
            )
            assert_current(osd_state.absent(claimed_id, profile=_PROFILE))

            service_opts["test"] = True
            service_plan = service_state.absent(service_name, profile=_PROFILE)
            assert service_plan["result"] is None, service_plan["comment"]
            service_opts["test"] = False
            refused = service_state.absent(service_name, profile=_PROFILE)
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert_changed(
                service_state.absent(
                    service_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
            )
            assert_current(service_state.absent(service_name, profile=_PROFILE))
        finally:
            osd_opts["test"] = False
            service_opts["test"] = False
            osd_absence_confirmed = False
            if claimed_id is None and create_submitted:
                current_inventory = _inventory(live_client, hostname)
                device = _target_device(current_inventory, device_path)
                if (
                    isinstance(device.get("osd_ids"), list)
                    and len(device["osd_ids"]) == 1
                    and isinstance(device.get("lvs"), list)
                    and device["lvs"]
                ):
                    claimed_id = live_client.claim_created_osds(current_inventory)[0]

            current_service = _owned_osd_service(
                live_client,
                service_name,
                service_id,
                hostname,
                device_path,
            )
            if current_service is not None:
                _disable_redeployment(
                    live_client,
                    service_name,
                    service_id,
                    hostname,
                    device_path,
                    spec,
                    service_opts,
                )

            if claimed_id is not None:
                _cleanup_osd_absence(claimed_id)
                osd_absence_confirmed = True

            if (
                _owned_osd_service(
                    live_client,
                    service_name,
                    service_id,
                    hostname,
                    device_path,
                )
                is not None
            ):
                if claimed_id is None:
                    device = _target_device(
                        _inventory(live_client, hostname),
                        device_path,
                    )
                    osd_absence_confirmed = (
                        device.get("osd_ids") == [] and device.get("lvs", []) == []
                    )
                if not osd_absence_confirmed:
                    pytest.fail(
                        "OSD ownership could not be proven or the OSD remains; "
                        "the unmanaged service was retained for safe recovery"
                    )
                result = service_state.absent(
                    service_name,
                    confirm=True,
                    profile=_PROFILE,
                    task_interval=0.5,
                )
                assert result["result"] is True, result["comment"]
