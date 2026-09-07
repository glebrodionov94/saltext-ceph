from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.integration import _live
from tests.integration import conftest as live_conftest

FSID = "11111111-2222-4333-8444-555555555555"
HOST = "ceph-node-02"
OTHER_HOST = "ceph-node-03"
SERVICE = "rgw.saltext-ci-live-rgw"
OSD_SERVICE = "osd.saltext-ci-live-sdb"
DEVICE = "/dev/sdb"
DEVICE_ID = "scsi-3600508b400105e210000900000490000"


def _guard(*allowlisted, declared=()):
    environment = {
        "CEPH_TEST_URL": "https://ceph.example.test:8443",
        "CEPH_TEST_TOKEN": "header.payload.signature",
        "CEPH_TEST_EXPECTED_FSID": FSID,
        "CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID": FSID,
        "CEPH_TEST_DESTRUCTIVE_ALLOWLIST": ",".join(allowlisted),
    }
    settings = _live.load_settings(
        live=True,
        mutate=True,
        destructive=True,
        environ=environment,
    )
    transport = Mock(config=settings.connection, closed=False)
    transport.request.return_value = object()
    client = _live.GuardedLiveClient(
        transport,
        settings,
        level="destructive",
        destructive_resources=declared,
    )
    return client, transport, settings


def _inventory(*, hostname=HOST, path=DEVICE, device_id="", **updates):
    device = {
        "path": path,
        "available": True,
        "osd_ids": [],
        "rejected_reasons": [],
        "device_id": device_id,
    }
    device.update(updates)
    return {"name": hostname, "devices": [device]}


def _service_spec(*, unmanaged=True):
    return {
        "service_type": "rgw",
        "service_id": "saltext-ci-live-rgw",
        "placement": {"hosts": [HOST]},
        "unmanaged": unmanaged,
    }


def _drive_group(path=DEVICE):
    return {
        "service_type": "osd",
        "service_id": "saltext-ci-live-sdb",
        "placement": {"hosts": [HOST]},
        "data_devices": {"paths": [path]},
        "encrypted": False,
    }


def _osd_payload(group=None):
    return {
        "method": "drive_groups",
        "data": [_drive_group() if group is None else group],
        "tracking_id": OSD_SERVICE,
    }


def _post_create_inventory(
    *,
    hostname=HOST,
    path=DEVICE,
    device_id="",
    osd_ids=None,
    affinity="saltext-ci-live-sdb",
    lv_osd_id=7,
):
    if osd_ids is None:
        osd_ids = [7]
    return {
        "name": hostname,
        "devices": [
            {
                "path": path,
                "available": False,
                "device_id": device_id,
                "osd_ids": osd_ids,
                "lvs": [{"osd_id": lv_osd_id, "osdspec_affinity": affinity}],
            }
        ],
    }


def test_dynamic_destructive_marker_defers_membership_but_not_write_authorization():
    resource = f"host:{HOST}"
    client, transport, settings = _guard(resource)

    settings.require_destructive_gate()
    with pytest.raises(_live.LiveConfigurationError, match="no active infrastructure lease"):
        client.request(
            "POST",
            "/api/host",
            api_version="0.1",
            data={"hostname": HOST},
        )

    transport.request.assert_not_called()


def test_resource_less_destructive_marker_passes_setup_gate_only():
    resource = f"host:{HOST}"
    client, transport, settings = _guard(resource)
    node = Mock()
    node.iter_markers.side_effect = lambda name: iter(())
    node.get_closest_marker.side_effect = lambda name: (
        SimpleNamespace(args=(), kwargs={}) if name == "ceph_live_destructive" else None
    )
    request = Mock(node=node)
    request.getfixturevalue.return_value = settings

    live_conftest._enforce_live_requirements.__wrapped__(request)

    with pytest.raises(_live.LiveConfigurationError, match="no active infrastructure lease"):
        client.request(
            "POST",
            "/api/host",
            api_version="0.1",
            data={"hostname": HOST},
        )
    transport.request.assert_not_called()


def test_every_lease_resource_must_be_exactly_allowlisted():
    resource = f"host:{HOST}"
    client, transport, _ = _guard(resource)

    with pytest.raises(_live.LiveConfigurationError, match="absent from"):
        with client.infrastructure_lease(resource, f"host:{OTHER_HOST}"):
            pass

    transport.request.assert_not_called()


def test_static_marker_caps_the_runtime_lease():
    resource = f"host:{HOST}"
    other = f"host:{OTHER_HOST}"
    client, transport, _ = _guard(resource, other, declared=(resource,))

    with pytest.raises(_live.LiveConfigurationError, match="exceeds the resources declared"):
        with client.infrastructure_lease(resource, other):
            pass

    transport.request.assert_not_called()


@pytest.mark.parametrize(
    "resource",
    [
        "host:node-*",
        "host:../../node",
        "osd:01",
        "device:ceph-node-02:/dev/../sdb",
        "device:ceph-node-02:/dev/sd*",
        "device:ceph-node-02:/etc/passwd",
        "unknown:value",
    ],
)
def test_infrastructure_lease_rejects_noncanonical_identifiers(resource):
    safe = f"host:{HOST}"
    with pytest.raises(_live.LiveConfigurationError):
        client, _, _ = _guard(safe, resource)
        with client.infrastructure_lease(resource):
            pass


def test_host_routes_accept_only_the_exact_leased_host_and_payloads():
    resource = f"host:{HOST}"
    client, transport, _ = _guard(resource, declared=(resource,))
    expected = transport.request.return_value

    with client.infrastructure_lease(resource):
        assert (
            client.request(
                "POST",
                "/api/host",
                api_version="0.1",
                data={
                    "hostname": HOST,
                    "addr": "10.0.0.12",
                    "labels": ["saltext-ci", "storage"],
                },
            )
            is expected
        )
        client.request(
            "PUT",
            f"/api/host/{HOST}",
            api_version="0.1",
            data={"update_labels": True, "labels": ["saltext-ci-updated"]},
        )
        client.request(
            "PUT",
            f"/api/host/{HOST}",
            api_version="0.1",
            data={"maintenance": True, "force": False},
        )
        client.request(
            "PUT",
            f"/api/host/{HOST}",
            api_version="0.1",
            data={"drain": True},
        )
        client.request("DELETE", f"/api/host/{HOST}", api_version="1.0")

    assert transport.request.call_count == 5


@pytest.mark.parametrize(
    "method,path,version,params,data",
    [
        ("POST", "/api/host", "1.0", None, {"hostname": HOST}),
        ("POST", "/api/host", "0.1", {}, {"hostname": HOST}),
        ("POST", "/api/host", "0.1", None, {"hostname": OTHER_HOST}),
        ("POST", "/api/host", "0.1", None, {"hostname": HOST, "extra": True}),
        (
            "PUT",
            f"/api/host/{HOST}",
            "0.1",
            None,
            {"update_labels": False, "labels": ["storage"]},
        ),
        ("PUT", f"/api/host/{HOST}", "0.1", None, {"drain": False}),
        ("DELETE", f"/api/host/{OTHER_HOST}", "1.0", None, None),
        ("DELETE", f"/api/host/{HOST}", "1.0", {"force": True}, None),
    ],
)
def test_host_guard_rejects_route_version_query_identity_and_body_mismatches(
    method, path, version, params, data
):
    resource = f"host:{HOST}"
    client, transport, _ = _guard(resource)

    with client.infrastructure_lease(resource):
        with pytest.raises(_live.LiveConfigurationError):
            client.request(method, path, api_version=version, params=params, data=data)

    transport.request.assert_not_called()


def test_service_routes_bind_identity_and_every_placement_host():
    resources = (f"service:{SERVICE}", f"host:{HOST}")
    client, transport, _ = _guard(*resources)

    with client.infrastructure_lease(*resources):
        client.request(
            "POST",
            "/api/service",
            api_version="1.0",
            data={"service_name": SERVICE, "service_spec": _service_spec()},
        )
        client.request(
            "PUT",
            f"/api/service/{SERVICE}",
            api_version="1.0",
            data={"service_spec": _service_spec(unmanaged=False)},
        )
        client.request("DELETE", f"/api/service/{SERVICE}", api_version="1.0")

    assert transport.request.call_count == 3


@pytest.mark.parametrize(
    "service_name,spec",
    [
        (
            "mon",
            {"service_type": "mon", "placement": {"hosts": [HOST]}},
        ),
        (
            SERVICE,
            {
                "service_type": "rgw",
                "service_id": "saltext-ci-live-rgw",
                "placement": {"host_pattern": "*"},
            },
        ),
        (
            SERVICE,
            {
                "service_type": "rgw",
                "service_id": "saltext-ci-live-rgw",
                "placement": {"hosts": ["*"]},
            },
        ),
        (
            SERVICE,
            {
                "service_type": "rgw",
                "service_id": "other",
                "placement": {"hosts": [HOST]},
            },
        ),
        (
            SERVICE,
            {
                **_service_spec(),
                "spec": {"rgw_frontend_port": 8080},
            },
        ),
    ],
)
def test_service_guard_rejects_core_pattern_mismatched_and_extra_specs(service_name, spec):
    resources = (f"service:{SERVICE}", f"service:{service_name}", f"host:{HOST}")
    resources = tuple(dict.fromkeys(resources))
    client, transport, _ = _guard(*resources)

    with client.infrastructure_lease(*resources):
        with pytest.raises(_live.LiveConfigurationError):
            client.request(
                "POST",
                "/api/service",
                api_version="1.0",
                data={"service_name": service_name, "service_spec": spec},
            )

    transport.request.assert_not_called()


def test_service_placement_cannot_use_an_unleased_host():
    resources = (f"service:{SERVICE}", f"host:{HOST}")
    client, transport, _ = _guard(*resources)
    spec = _service_spec()
    spec["placement"] = {"hosts": [OTHER_HOST]}

    with client.infrastructure_lease(*resources):
        with pytest.raises(_live.LiveConfigurationError, match="exceeds its infrastructure lease"):
            client.request(
                "POST",
                "/api/service",
                api_version="1.0",
                data={"service_name": SERVICE, "service_spec": spec},
            )

    transport.request.assert_not_called()


def test_osd_create_requires_one_exact_available_device_and_forwards_expected_payload():
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)
    payload = _osd_payload()

    with client.infrastructure_lease(*resources, device_inventory=_inventory()):
        client.request("POST", "/api/osd", api_version="1.0", data=payload)

    transport.request.assert_called_once_with(
        "POST",
        "/api/osd",
        api_version="1.0",
        params=None,
        data=payload,
    )


def test_osd_service_can_only_be_made_unmanaged_with_its_exact_drive_group():
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)
    spec = _drive_group()
    spec["unmanaged"] = True

    with client.infrastructure_lease(*resources, device_inventory=_inventory()):
        client.request(
            "PUT",
            f"/api/service/{OSD_SERVICE}",
            api_version="1.0",
            data={"service_spec": spec},
        )

    transport.request.assert_called_once_with(
        "PUT",
        f"/api/service/{OSD_SERVICE}",
        api_version="1.0",
        params=None,
        data={"service_spec": spec},
    )


@pytest.mark.parametrize("change", ("managed", "missing-unmanaged", "other-device", "other-host"))
def test_osd_service_update_rejects_managed_or_changed_drive_groups(change):
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)
    spec = _drive_group()
    if change == "managed":
        spec["unmanaged"] = False
    elif change == "missing-unmanaged":
        pass
    elif change == "other-device":
        spec["unmanaged"] = True
        spec["data_devices"] = {"paths": ["/dev/sdc"]}
    else:
        spec["unmanaged"] = True
        spec["placement"] = {"hosts": [OTHER_HOST]}

    with client.infrastructure_lease(*resources, device_inventory=_inventory()):
        with pytest.raises(_live.LiveConfigurationError):
            client.request(
                "PUT",
                f"/api/service/{OSD_SERVICE}",
                api_version="1.0",
                data={"service_spec": spec},
            )

    transport.request.assert_not_called()


def test_osd_service_update_rejects_a_different_leased_service_body():
    other_service = "osd.saltext-ci-other"
    resources = (
        f"service:{OSD_SERVICE}",
        f"service:{other_service}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)
    spec = _drive_group()
    spec["service_id"] = "saltext-ci-other"
    spec["unmanaged"] = True

    with client.infrastructure_lease(*resources, device_inventory=_inventory()):
        with pytest.raises(_live.LiveConfigurationError):
            client.request(
                "PUT",
                f"/api/service/{OSD_SERVICE}",
                api_version="1.0",
                data={"service_spec": spec},
            )

    transport.request.assert_not_called()


def test_osd_device_id_is_part_of_the_lease_when_inventory_exposes_one():
    base_resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    identity_resource = f"device-id:{HOST}:{DEVICE_ID}"
    client, transport, _ = _guard(*base_resources, identity_resource)

    with pytest.raises(_live.LiveConfigurationError, match="identity is absent"):
        with client.infrastructure_lease(
            *base_resources,
            device_inventory=_inventory(device_id=DEVICE_ID),
        ):
            pass

    with client.infrastructure_lease(
        *base_resources,
        identity_resource,
        device_inventory=_inventory(device_id=DEVICE_ID),
    ):
        client.request("POST", "/api/osd", api_version="1.0", data=_osd_payload())

    assert transport.request.call_count == 1


def test_new_osd_id_can_be_claimed_only_from_same_lease_provenance():
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)

    with client.infrastructure_lease(*resources, device_inventory=_inventory()):
        with pytest.raises(_live.LiveConfigurationError, match="No successful guarded"):
            client.claim_created_osds(_post_create_inventory())

        client.request("POST", "/api/osd", api_version="1.0", data=_osd_payload())
        assert client.claim_created_osds(_post_create_inventory()) == (7,)
        client.request(
            "PUT",
            "/api/osd/7",
            api_version="1.0",
            data={"device_class": "saltext_ci"},
        )
        client.request(
            "DELETE",
            "/api/osd/7",
            api_version="1.0",
            params={"preserve_id": False, "force": False},
        )

    assert transport.request.call_count == 3


@pytest.mark.parametrize(
    "post_inventory",
    [
        _post_create_inventory(hostname=OTHER_HOST),
        _post_create_inventory(path="/dev/sdc"),
        _post_create_inventory(osd_ids=[]),
        _post_create_inventory(osd_ids=[7, 8]),
        _post_create_inventory(osd_ids=[7], lv_osd_id=8),
        _post_create_inventory(affinity="someone-else"),
    ],
)
def test_created_osd_claim_rejects_mismatched_host_device_ids_and_affinity(post_inventory):
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)

    with client.infrastructure_lease(*resources, device_inventory=_inventory()):
        client.request("POST", "/api/osd", api_version="1.0", data=_osd_payload())
        with pytest.raises(_live.LiveConfigurationError):
            client.claim_created_osds(post_inventory)
        with pytest.raises(_live.LiveConfigurationError):
            client.request(
                "DELETE",
                "/api/osd/7",
                api_version="1.0",
                params={"preserve_id": False, "force": False},
            )

    assert transport.request.call_count == 1


def test_created_osd_claim_preserves_nonempty_device_identity():
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
        f"device-id:{HOST}:{DEVICE_ID}",
    )
    client, transport, _ = _guard(*resources)

    with client.infrastructure_lease(
        *resources,
        device_inventory=_inventory(device_id=DEVICE_ID),
    ):
        client.request("POST", "/api/osd", api_version="1.0", data=_osd_payload())
        with pytest.raises(_live.LiveConfigurationError, match="identity changed"):
            client.claim_created_osds(_post_create_inventory(device_id="other-device"))

    assert transport.request.call_count == 1


def test_failed_osd_post_does_not_create_a_provenance_lease():
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)
    transport.request.side_effect = RuntimeError("synthetic transport failure")

    with client.infrastructure_lease(*resources, device_inventory=_inventory()):
        with pytest.raises(RuntimeError, match="synthetic"):
            client.request("POST", "/api/osd", api_version="1.0", data=_osd_payload())
        with pytest.raises(_live.LiveConfigurationError, match="No successful guarded"):
            client.claim_created_osds(_post_create_inventory())

    assert transport.request.call_count == 1


@pytest.mark.parametrize(
    "inventory",
    [
        _inventory(hostname=OTHER_HOST),
        _inventory(available=False),
        _inventory(osd_ids=[4]),
        _inventory(rejected_reasons=["locked"]),
        _inventory(path="/dev/sdc"),
    ],
)
def test_osd_inventory_evidence_must_match_an_empty_available_leased_device(inventory):
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)

    with pytest.raises(_live.LiveConfigurationError):
        with client.infrastructure_lease(*resources, device_inventory=inventory):
            client.request("POST", "/api/osd", api_version="1.0", data=_osd_payload())

    transport.request.assert_not_called()


def test_osd_create_cannot_use_a_device_without_fresh_inventory_evidence():
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)

    with client.infrastructure_lease(*resources):
        with pytest.raises(_live.LiveConfigurationError, match="fresh available-device"):
            client.request("POST", "/api/osd", api_version="1.0", data=_osd_payload())

    transport.request.assert_not_called()


def _dangerous_osd_payloads():
    all_devices = _drive_group()
    all_devices["data_devices"] = {"all": True}
    mixed_selector = _drive_group()
    mixed_selector["data_devices"] = {"paths": [DEVICE], "all": True}
    host_pattern = _drive_group()
    host_pattern["placement"] = {"host_pattern": "*"}
    wildcard_host = _drive_group()
    wildcard_host["placement"] = {"hosts": ["*"]}
    multiple_paths = _drive_group()
    multiple_paths["data_devices"] = {"paths": [DEVICE, "/dev/sdc"]}
    unmanaged = _drive_group()
    unmanaged["unmanaged"] = True
    filtered = _drive_group()
    filtered["filter_logic"] = "AND"
    second = deepcopy(_drive_group())
    return [
        {"method": "predefined", "data": [{"option": "cost_capacity"}], "tracking_id": OSD_SERVICE},
        {"method": "bare", "data": {"svc_id": 7}, "tracking_id": OSD_SERVICE},
        _osd_payload(all_devices),
        _osd_payload(mixed_selector),
        _osd_payload(host_pattern),
        _osd_payload(wildcard_host),
        _osd_payload(multiple_paths),
        _osd_payload(unmanaged),
        _osd_payload(filtered),
        _osd_payload(_drive_group("/dev/../sdb")),
        _osd_payload(_drive_group("/dev/sd*")),
        {"method": "drive_groups", "data": [_drive_group(), second], "tracking_id": OSD_SERVICE},
        {"method": "drive_groups", "data": [_drive_group()], "tracking_id": "other"},
    ]


@pytest.mark.parametrize("payload", _dangerous_osd_payloads())
def test_osd_create_rejects_broad_selectors_wildcards_and_alternate_methods(payload):
    resources = (
        f"service:{OSD_SERVICE}",
        f"host:{HOST}",
        f"device:{HOST}:{DEVICE}",
    )
    client, transport, _ = _guard(*resources)

    with client.infrastructure_lease(*resources, device_inventory=_inventory()):
        with pytest.raises(_live.LiveConfigurationError):
            client.request("POST", "/api/osd", api_version="1.0", data=payload)

    transport.request.assert_not_called()


def test_osd_item_routes_are_bound_to_one_canonical_numeric_id():
    resource = "osd:7"
    client, transport, _ = _guard(resource)

    with client.infrastructure_lease(resource):
        client.request(
            "PUT",
            "/api/osd/7",
            api_version="1.0",
            data={"device_class": "saltext_ci"},
        )
        client.request(
            "DELETE",
            "/api/osd/7",
            api_version="1.0",
            params={"preserve_id": False, "force": False},
        )

    assert transport.request.call_count == 2


@pytest.mark.parametrize(
    "method,path,params,data",
    [
        ("DELETE", "/api/osd/8", {"preserve_id": False, "force": False}, None),
        ("DELETE", "/api/osd/7", {"preserve_id": False}, None),
        ("DELETE", "/api/osd/7", {"preserve_id": False, "force": "false"}, None),
        ("DELETE", "/api/osd/7", {"preserve_id": False, "force": False}, {}),
        ("PUT", "/api/osd/7", None, {"device_class": "hdd", "extra": True}),
        ("POST", "/api/osd/7/scrub", None, {"deep": False}),
    ],
)
def test_osd_item_guard_rejects_other_ids_partial_queries_extra_data_and_actions(
    method, path, params, data
):
    resource = "osd:7"
    client, transport, _ = _guard(resource)

    with client.infrastructure_lease(resource):
        with pytest.raises(_live.LiveConfigurationError):
            client.request(method, path, api_version="1.0", params=params, data=data)

    transport.request.assert_not_called()


def test_infrastructure_lease_is_revoked_after_the_context_exits():
    resource = f"host:{HOST}"
    client, transport, _ = _guard(resource)

    with client.infrastructure_lease(resource):
        pass

    with pytest.raises(_live.LiveConfigurationError, match="no active infrastructure lease"):
        client.request("DELETE", f"/api/host/{HOST}", api_version="1.0")
    transport.request.assert_not_called()
