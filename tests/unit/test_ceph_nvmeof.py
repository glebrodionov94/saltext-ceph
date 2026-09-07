"""Current Ceph NVMe-oF Dashboard API contracts and Salt integration."""

import inspect
from unittest.mock import Mock

import pytest
import salt.loader

from saltext.ceph.modules import ceph_nvmeof as execution
from saltext.ceph.utils import ceph as ceph_utils
from saltext.ceph.utils.ceph import nvmeof
from saltext.ceph.utils.ceph import nvmeof_api
from saltext.ceph.utils.ceph import nvmeof_gateway
from saltext.ceph.utils.ceph import nvmeof_namespace
from saltext.ceph.utils.ceph import nvmeof_subsystem
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.client import CephClient
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.wrapper import ceph_nvmeof as wrapper

NQN = "nqn.2026-09.io.example:storage"
HOST_NQN = "nqn.2026-09.io.example:host1"


@pytest.fixture
def client():
    result = Mock()
    result.request.return_value = APIResponse(202, {"name": "nvmeof/task"})
    return result


def _endpoint_cases():
    return [
        (nvmeof_gateway.gateway_info, (), {}, "GET", "/api/nvmeof/gateway"),
        (nvmeof_gateway.gateway_groups, (), {}, "GET", "/api/nvmeof/gateway/group"),
        (
            nvmeof_gateway.gateway_version,
            (),
            {},
            "GET",
            "/api/nvmeof/gateway/version",
        ),
        (
            nvmeof_gateway.gateway_log_level,
            (),
            {},
            "GET",
            "/api/nvmeof/gateway/log_level",
        ),
        (
            nvmeof_gateway.gateway_set_log_level,
            ("INFO",),
            {},
            "PUT",
            "/api/nvmeof/gateway/log_level",
        ),
        (nvmeof_gateway.gateway_stats, (), {}, "GET", "/api/nvmeof/gateway/stats"),
        (
            nvmeof_gateway.gateway_listener_info,
            (NQN,),
            {},
            "GET",
            f"/api/nvmeof/gateway/listener_info/{NQN}",
        ),
        (
            nvmeof_gateway.gateway_set_io_stats,
            (True,),
            {},
            "PUT",
            "/api/nvmeof/gateway/io_stats",
        ),
        (
            nvmeof_gateway.gateway_thread_stats,
            (),
            {},
            "GET",
            "/api/nvmeof/gateway/thread_stats",
        ),
        (
            nvmeof_gateway.gateway_refresh_network,
            (),
            {"server_address": "gw1.example", "confirm": True},
            "PUT",
            "/api/nvmeof/gateway/refresh_network",
        ),
        (
            nvmeof_gateway.spdk_log_level,
            (),
            {},
            "GET",
            "/api/nvmeof/spdk/log_level",
        ),
        (
            nvmeof_gateway.spdk_set_log_level,
            ("INFO",),
            {},
            "PUT",
            "/api/nvmeof/spdk/log_level",
        ),
        (
            nvmeof_gateway.spdk_disable_log_level,
            (),
            {},
            "PUT",
            "/api/nvmeof/spdk/log_level/disable",
        ),
        (nvmeof_subsystem.subsystem_list, (), {}, "GET", "/api/nvmeof/subsystem"),
        (
            nvmeof_subsystem.subsystem_get,
            (NQN,),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}",
        ),
        (
            nvmeof_subsystem.subsystem_create,
            (NQN,),
            {},
            "POST",
            "/api/nvmeof/subsystem",
        ),
        (
            nvmeof_subsystem.subsystem_delete,
            (NQN,),
            {"confirm": True},
            "DELETE",
            f"/api/nvmeof/subsystem/{NQN}",
        ),
        (
            nvmeof_subsystem.subsystem_change_key,
            (NQN, "DHHC-1:01:secret"),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/change_key",
        ),
        (
            nvmeof_subsystem.listener_list,
            (NQN,),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}/listener",
        ),
        (
            nvmeof_subsystem.listener_create,
            (NQN, "gw1", "192.0.2.10"),
            {},
            "POST",
            f"/api/nvmeof/subsystem/{NQN}/listener",
        ),
        (
            nvmeof_subsystem.listener_delete,
            (NQN, "gw1", "192.0.2.10", 4420),
            {"confirm": True},
            "DELETE",
            f"/api/nvmeof/subsystem/{NQN}/listener/gw1/192.0.2.10/4420",
        ),
        (
            nvmeof_subsystem.host_list,
            (NQN,),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}/host",
        ),
        (
            nvmeof_subsystem.host_create,
            (NQN, HOST_NQN),
            {},
            "POST",
            f"/api/nvmeof/subsystem/{NQN}/host",
        ),
        (
            nvmeof_subsystem.host_delete,
            (NQN, HOST_NQN),
            {"confirm": True},
            "DELETE",
            f"/api/nvmeof/subsystem/{NQN}/host/{HOST_NQN}",
        ),
        (
            nvmeof_subsystem.host_change_key,
            (NQN, HOST_NQN, "DHHC-1:01:secret"),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/host/{HOST_NQN}/change_key",
        ),
        (
            nvmeof_subsystem.host_change_controller_key,
            (NQN, HOST_NQN, "DHHC-1:01:controller"),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/host/{HOST_NQN}/change_controller_key",
        ),
        (
            nvmeof_subsystem.host_delete_key,
            (NQN, HOST_NQN),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/host/{HOST_NQN}/del_key",
        ),
        (
            nvmeof_subsystem.host_delete_controller_key,
            (NQN, HOST_NQN),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/host/{HOST_NQN}/del_controller_key",
        ),
        (
            nvmeof_subsystem.connection_list,
            (NQN,),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}/connection",
        ),
        (
            nvmeof_namespace.namespace_list,
            (NQN,),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}/namespace",
        ),
        (
            nvmeof_namespace.namespace_get,
            (NQN, 1),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1",
        ),
        (
            nvmeof_namespace.namespace_io_stats,
            (NQN, 1),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/io_stats",
        ),
        (
            nvmeof_namespace.namespace_create,
            (NQN, "image1"),
            {},
            "POST",
            f"/api/nvmeof/subsystem/{NQN}/namespace",
        ),
        (
            nvmeof_namespace.namespace_set_qos,
            (NQN, 1),
            {"rw_ios_per_second": 1000},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/set_qos",
        ),
        (
            nvmeof_namespace.namespace_change_load_balancing_group,
            (NQN, 1, 2),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/change_load_balancing_group",
        ),
        (
            nvmeof_namespace.namespace_resize,
            (NQN, 1, 1 << 30),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/resize",
        ),
        (
            nvmeof_namespace.namespace_add_host,
            (NQN, 1, HOST_NQN),
            {},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/add_host",
        ),
        (
            nvmeof_namespace.namespace_delete_host,
            (NQN, 1, HOST_NQN),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/del_host",
        ),
        (
            nvmeof_namespace.namespace_change_visibility,
            (NQN, 1, False),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/change_visibility",
        ),
        (
            nvmeof_namespace.namespace_change_location,
            (NQN, 1, "rack-a"),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/change_location",
        ),
        (
            nvmeof_namespace.namespace_list_hosts,
            (NQN,),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}/namespace/list_hosts",
        ),
        (
            nvmeof_namespace.namespace_list_locations,
            (NQN,),
            {},
            "GET",
            f"/api/nvmeof/subsystem/{NQN}/namespace/list_locations",
        ),
        (
            nvmeof_namespace.namespace_set_auto_resize,
            (NQN, 1, True),
            {},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/set_auto_resize",
        ),
        (
            nvmeof_namespace.namespace_set_rbd_trash_image,
            (NQN, 1, True),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/set_rbd_trash_image",
        ),
        (
            nvmeof_namespace.namespace_refresh_size,
            (NQN, 1),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/refresh_size",
        ),
        (
            nvmeof_namespace.namespace_unpin,
            (NQN, 1),
            {"confirm": True},
            "PUT",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1/unpin",
        ),
        (
            nvmeof_namespace.namespace_update,
            (NQN, 1),
            {"rw_ios_per_second": 1000, "confirm": True},
            "PATCH",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1",
        ),
        (
            nvmeof_namespace.namespace_delete,
            (NQN, 1),
            {"confirm": True},
            "DELETE",
            f"/api/nvmeof/subsystem/{NQN}/namespace/1",
        ),
    ]


@pytest.mark.parametrize("function,args,kwargs,method,path", _endpoint_cases())
def test_all_current_public_api_routes_use_version_1(client, function, args, kwargs, method, path):
    result = function(client, *args, **kwargs)
    assert result.status == 202
    assert client.request.call_count == 1
    path = path.replace(NQN, nvmeof.encoded(NQN)).replace(HOST_NQN, nvmeof.encoded(HOST_NQN))
    assert client.request.call_args.args == (method, path)
    assert client.request.call_args.kwargs["api_version"] == "1.0"


def test_public_surface_is_exactly_48_api_endpoints_and_excludes_internal_routes():
    assert len(nvmeof_api.PUBLIC_OPERATIONS) == 48
    assert set(nvmeof_api.PUBLIC_OPERATIONS) == {case[0].__name__ for case in _endpoint_cases()}
    assert not {
        "subsystem_delete_key",
        "subsystem_add_network",
        "subsystem_delete_network",
        "subsystem_add_kmip_server_endpoint",
        "subsystem_delete_kmip_server_endpoint",
        "subsystem_list_kmip_server_endpoints",
        "connection_io_stats",
        "connection_reset_io_stats",
        "status",
        "initiator_add",
        "initiator_delete",
    }.intersection(nvmeof_api.PUBLIC_OPERATIONS)


def test_execution_and_salt_ssh_export_the_same_48_signatures():
    execution_names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    wrapper_names = {
        name
        for name, function in inspect.getmembers(wrapper, inspect.isfunction)
        if not name.startswith("_")
    }
    assert execution_names == wrapper_names == set(nvmeof_api.PUBLIC_OPERATIONS)
    for name in execution_names:
        assert inspect.signature(getattr(execution, name)) == inspect.signature(
            getattr(wrapper, name)
        )
        assert "CLI Example:" in getattr(execution, name).__doc__


def test_gateway_queries_and_payloads_match_current_controller(client):
    nvmeof_gateway.gateway_info(
        client,
        gw_group="alpha",
        server_address="https://gw1.example:5500",
    )
    assert client.request.call_args.kwargs["params"] == {
        "gw_group": "alpha",
        "server_address": "https://gw1.example:5500",
    }
    client.reset_mock()
    nvmeof_gateway.gateway_set_log_level(client, " WARNING ", traddr="legacy-gw")
    assert client.request.call_args.kwargs["data"] == {
        "log_level": "warning",
        "traddr": "legacy-gw",
    }
    client.reset_mock()
    nvmeof_gateway.spdk_set_log_level(
        client,
        log_level="debug",
        print_level="notice",
        extra_log_flags=["nvmf", "rdma"],
    )
    assert client.request.call_args.kwargs["data"] == {
        "log_level": "DEBUG",
        "print_level": "NOTICE",
        "extra_log_flags": ["nvmf", "rdma"],
    }


def test_subsystem_and_listener_send_complete_current_payloads(client):
    nvmeof_subsystem.subsystem_create(
        client,
        NQN,
        max_namespaces=32,
        no_group_append=True,
        serial_number="SN-1",
        dhchap_key="DHHC-1:01:secret",
        gw_group="alpha",
        network_mask=["192.0.2.0/24", "2001:db8::/64"],
        port=4420,
        secure_listeners=True,
        model_name="Ceph-NVMe",
    )
    assert client.request.call_args.kwargs["data"] == {
        "nqn": NQN,
        "max_namespaces": 32,
        "no_group_append": True,
        "serial_number": "SN-1",
        "dhchap_key": "DHHC-1:01:secret",
        "gw_group": "alpha",
        "network_mask": ["192.0.2.0/24", "2001:db8::/64"],
        "port": 4420,
        "secure_listeners": True,
        "model_name": "Ceph-NVMe",
    }
    client.reset_mock()
    nvmeof_subsystem.listener_create(
        client,
        NQN,
        "gw1",
        "2001:db8::10",
        trsvcid=4421,
        adrfam=1,
        secure=True,
        verify_host_name=True,
    )
    assert client.request.call_args.kwargs["data"] == {
        "host_name": "gw1",
        "traddr": "2001:db8::10",
        "trsvcid": 4421,
        "adrfam": 1,
        "secure": True,
        "force": False,
        "verify_host_name": True,
    }


def test_subsystem_filters_and_forced_listener_contract(client):
    nvmeof_subsystem.subsystem_list(
        client,
        nqn=NQN,
        serial_number="SN-1",
        traddr="legacy-gw",
    )
    assert client.request.call_args.kwargs["params"] == {
        "nqn": NQN,
        "serial_number": "SN-1",
        "traddr": "legacy-gw",
    }
    client.reset_mock()
    with pytest.raises(ConfigurationError, match="confirm=True"):
        nvmeof_subsystem.listener_create(
            client,
            NQN,
            "gw1",
            "192.0.2.10",
            force=True,
        )
    client.request.assert_not_called()
    nvmeof_subsystem.listener_create(
        client,
        NQN,
        "gw1",
        "192.0.2.10",
        force=True,
        confirm=True,
    )
    assert client.request.call_args.kwargs["data"]["force"] is True


def test_namespace_create_sends_current_main_fields_and_preserves_202(client):
    result = nvmeof_namespace.namespace_create(
        client,
        NQN,
        "image1",
        rbd_pool="rbd",
        rbd_data_pool="rbd-data",
        nsid="7",
        uuid="123e4567-e89b-12d3-a456-426614174000",
        create_image=True,
        rbd_image_size=1 << 30,
        trash_image=True,
        block_size=4096,
        load_balancing_group=2,
        no_auto_visible=True,
        disable_auto_resize=True,
        read_only=True,
        location="rack-a",
        rados_namespace="tenant",
        encryption_format=["LUKS2"],
        encryption_algorithm="AES-XTS",
        key_id=["vault-key-1"],
    )
    assert result.status == 202
    assert client.request.call_count == 1
    assert client.request.call_args.kwargs["data"] == {
        "rbd_image_name": "image1",
        "rbd_pool": "rbd",
        "rbd_data_pool": "rbd-data",
        "nsid": "7",
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "create_image": True,
        "rbd_image_size": 1 << 30,
        "trash_image": True,
        "block_size": 4096,
        "load_balancing_group": 2,
        "force": False,
        "no_auto_visible": True,
        "disable_auto_resize": True,
        "read_only": True,
        "location": "rack-a",
        "rados_namespace": "tenant",
        "encryption_format": ["luks2"],
        "encryption_algorithm": "aes-xts",
        "key_id": ["vault-key-1"],
    }


def test_namespace_filters_and_compound_patch_are_structured(client):
    nvmeof_namespace.namespace_list_hosts(
        client,
        NQN,
        nsid=7,
        uuid="123e4567-e89b-12d3-a456-426614174000",
        gw_group="alpha",
    )
    assert client.request.call_args.kwargs["params"] == {
        "nsid": "7",
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "gw_group": "alpha",
    }
    client.reset_mock()
    nvmeof_namespace.namespace_update(
        client,
        NQN,
        7,
        rbd_image_size=2 << 30,
        load_balancing_group=3,
        rw_ios_per_second=5000,
        trash_image=False,
        location="",
        confirm=True,
    )
    assert client.request.call_args.kwargs["data"] == {
        "rbd_image_size": 2 << 30,
        "load_balancing_group": 3,
        "rw_ios_per_second": 5000,
        "trash_image": False,
        "location": "",
    }


@pytest.mark.parametrize(
    "function,args,kwargs",
    [
        (nvmeof_gateway.gateway_refresh_network, (), {"server_address": "gw1"}),
        (nvmeof_subsystem.subsystem_delete, (NQN,), {}),
        (nvmeof_subsystem.subsystem_change_key, (NQN, "secret"), {}),
        (nvmeof_subsystem.listener_delete, (NQN, "gw1", "192.0.2.1", 4420), {}),
        (nvmeof_subsystem.host_delete, (NQN, HOST_NQN), {}),
        (nvmeof_subsystem.host_change_key, (NQN, HOST_NQN, "secret"), {}),
        (nvmeof_subsystem.host_delete_key, (NQN, HOST_NQN), {}),
        (nvmeof_namespace.namespace_resize, (NQN, 1, 1024), {}),
        (nvmeof_namespace.namespace_delete_host, (NQN, 1, HOST_NQN), {}),
        (nvmeof_namespace.namespace_change_visibility, (NQN, 1, False), {}),
        (nvmeof_namespace.namespace_change_location, (NQN, 1, "rack-a"), {}),
        (nvmeof_namespace.namespace_set_rbd_trash_image, (NQN, 1, True), {}),
        (nvmeof_namespace.namespace_refresh_size, (NQN, 1), {}),
        (nvmeof_namespace.namespace_unpin, (NQN, 1), {}),
        (nvmeof_namespace.namespace_update, (NQN, 1), {"rw_ios_per_second": 1}),
        (nvmeof_namespace.namespace_delete, (NQN, 1), {}),
    ],
)
def test_disruptive_operations_require_exact_confirmation(
    client,
    function,
    args,
    kwargs,
):
    with pytest.raises(ConfigurationError, match="confirm=True"):
        function(client, *args, **kwargs)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "call",
    [
        lambda client: nvmeof_gateway.gateway_info(client, server_address="gw1", traddr="gw2"),
        lambda client: nvmeof_gateway.gateway_set_io_stats(client, "true"),
        lambda client: nvmeof_gateway.gateway_refresh_network(client, confirm=True),
        nvmeof_gateway.spdk_set_log_level,
        lambda client: nvmeof_subsystem.subsystem_get(client, "bad"),
        lambda client: nvmeof_subsystem.subsystem_create(
            client, NQN, network_mask=["not-a-network"]
        ),
        lambda client: nvmeof_subsystem.listener_create(
            client, NQN, "gw1", "2001:db8::1", adrfam=0
        ),
        lambda client: nvmeof_subsystem.listener_create(client, NQN, "gw1", "192.0.2.1", trsvcid=0),
        lambda client: nvmeof_namespace.namespace_get(client, NQN, True),
        lambda client: nvmeof_namespace.namespace_get(client, NQN, 0),
        lambda client: nvmeof_namespace.namespace_create(
            client, NQN, "image1", size=1, rbd_image_size=2
        ),
        lambda client: nvmeof_namespace.namespace_create(
            client, NQN, "image1", encryption_format=["LUKS2"], key_id=[]
        ),
        lambda client: nvmeof_namespace.namespace_create(
            client, NQN, "image1", encryption_format=["plain"], key_id=["key1"]
        ),
        lambda client: nvmeof_namespace.namespace_create(
            client, NQN, "image1", encryption_algorithm=1
        ),
        lambda client: nvmeof_namespace.namespace_create(
            client,
            NQN,
            "image1",
            encryption_format=["LUKS2", "luks2"],
            key_id=["key1", "key2"],
        ),
        lambda client: nvmeof_namespace.namespace_create(
            client, NQN, "image1", encryption_format=["LUKS2"], key_id=[" "]
        ),
        lambda client: nvmeof_namespace.namespace_set_qos(client, NQN, 1),
        lambda client: nvmeof_namespace.namespace_set_qos(client, NQN, 1, rw_ios_per_second=-1),
        lambda client: nvmeof_namespace.namespace_update(client, NQN, 1, confirm=True),
    ],
)
def test_invalid_values_fail_before_http(client, call):
    with pytest.raises(ConfigurationError):
        call(client)
    client.request.assert_not_called()


def test_secret_files_are_read_before_client_creation_and_responses_are_redacted(
    tmp_path,
    monkeypatch,
    client,
):
    source = tmp_path / "dhchap.key"
    source.write_text("DHHC-1:01:super-secret\n", encoding="utf-8")
    client.request.return_value = APIResponse(
        201,
        {
            "nqn": NQN,
            "dhchap_key": "DHHC-1:01:super-secret",
            "nested": {"psk": "private", "has_dhchap_key": True},
        },
    )
    get_client = Mock(return_value=client)
    monkeypatch.setattr(nvmeof_api.ceph, "get_client", get_client)

    result = nvmeof_api.subsystem_create(
        {},
        {},
        {},
        NQN,
        dhchap_key_source=source,
    )
    assert result["data"] == {
        "nqn": NQN,
        "nested": {"has_dhchap_key": True},
    }
    assert client.request.call_args.kwargs["data"]["dhchap_key"] == ("DHHC-1:01:super-secret")

    get_client.reset_mock()
    client.reset_mock()
    with pytest.raises(ConfigurationError, match="absolute regular file"):
        nvmeof_api.subsystem_change_key({}, {}, {}, NQN, "relative.key", confirm=True)
    get_client.assert_not_called()
    client.request.assert_not_called()


def test_multiline_secret_is_rejected_without_http(tmp_path, monkeypatch, client):
    source = tmp_path / "dhchap.key"
    source.write_text("first\nsecond\n", encoding="utf-8")
    get_client = Mock(return_value=client)
    monkeypatch.setattr(nvmeof_api.ceph, "get_client", get_client)
    with pytest.raises(ConfigurationError, match="single-line"):
        nvmeof_api.host_change_key(
            {},
            {},
            {},
            NQN,
            HOST_NQN,
            source,
            confirm=True,
        )
    get_client.assert_not_called()
    client.request.assert_not_called()


def test_all_host_secret_operations_read_files_and_strip_returned_keys(
    tmp_path,
    monkeypatch,
    client,
):
    sources = {}
    for name, value in {
        "host": "DHHC-1:01:host-secret",
        "controller": "DHHC-1:01:controller-secret",
        "psk": "NVMeTLSkey-1:01:psk-secret",
    }.items():
        source = tmp_path / f"{name}.key"
        source.write_text(value + "\n", encoding="utf-8")
        sources[name] = source
    client.request.return_value = APIResponse(
        200,
        {"host_nqn": HOST_NQN, "dhchap_controller_key": "must-not-return"},
    )
    monkeypatch.setattr(nvmeof_api.ceph, "get_client", Mock(return_value=client))

    result = nvmeof_api.host_create(
        {},
        {},
        {},
        NQN,
        HOST_NQN,
        dhchap_key_source=sources["host"],
        dhchap_controller_key_source=sources["controller"],
        psk_source=sources["psk"],
    )
    assert result["data"] == {"host_nqn": HOST_NQN}
    assert client.request.call_args.kwargs["data"] == {
        "host_nqn": HOST_NQN,
        "dhchap_key": "DHHC-1:01:host-secret",
        "dhchap_controller_key": "DHHC-1:01:controller-secret",
        "psk": "NVMeTLSkey-1:01:psk-secret",
    }

    client.reset_mock()
    nvmeof_api.subsystem_change_key({}, {}, {}, NQN, sources["host"], confirm=True)
    assert client.request.call_args.kwargs["data"]["dhchap_key"] == "DHHC-1:01:host-secret"
    client.reset_mock()
    nvmeof_api.host_change_key({}, {}, {}, NQN, HOST_NQN, sources["host"], confirm=True)
    assert client.request.call_args.kwargs["data"]["dhchap_key"] == "DHHC-1:01:host-secret"
    client.reset_mock()
    nvmeof_api.host_change_controller_key(
        {},
        {},
        {},
        NQN,
        HOST_NQN,
        sources["controller"],
        confirm=True,
    )
    assert client.request.call_args.kwargs["data"]["dhchap_controller_key"] == (
        "DHHC-1:01:controller-secret"
    )


def test_generic_dispatch_refuses_secret_and_unknown_operation(monkeypatch):
    get_client = Mock()
    monkeypatch.setattr(nvmeof_api.ceph, "get_client", get_client)
    for operation in ("subsystem_create", "missing"):
        with pytest.raises(ConfigurationError, match="Unknown or secret-bearing"):
            nvmeof_api.call({}, {}, {}, operation)
    get_client.assert_not_called()


def test_execution_and_wrapper_choose_the_correct_pillar_boundary(monkeypatch):
    execution_calls = []
    wrapper_calls = []
    monkeypatch.setattr(execution, "__opts__", {"id": "minion"}, raising=False)
    monkeypatch.setattr(execution, "__pillar__", {"trusted": True}, raising=False)
    monkeypatch.setattr(execution, "__context__", {}, raising=False)
    monkeypatch.setattr(wrapper, "__opts__", {"id": "controller"}, raising=False)
    monkeypatch.setattr(wrapper, "__context__", {}, raising=False)

    def execution_invoke(function, *args, **kwargs):
        execution_calls.append((function, args, kwargs))
        return "execution"

    def wrapper_invoke(function, *args, **kwargs):
        wrapper_calls.append((function, args, kwargs))
        return "wrapper"

    monkeypatch.setattr(execution._salt_adapter, "invoke", execution_invoke)
    assert execution.gateway_info(gw_group="alpha", profile="ops") == "execution"
    assert execution_calls[0][0] is nvmeof_api.call
    assert execution_calls[0][1][1] == {"trusted": True}
    assert execution_calls[0][2]["profile"] == "ops"
    assert execution.subsystem_change_key(NQN, "C:/secret", confirm=True) == "execution"
    assert execution_calls[1][0] is nvmeof_api.subsystem_change_key
    assert execution_calls[1][1][1] == {"trusted": True}

    monkeypatch.setattr(wrapper._salt_adapter, "invoke", wrapper_invoke)
    assert wrapper.host_create(NQN, HOST_NQN, psk_source="C:/secret", profile="ops") == ("wrapper")
    assert wrapper_calls[0][0] is nvmeof_api.host_create
    assert wrapper_calls[0][1][1] == {}
    assert wrapper_calls[0][2]["profile"] == "ops"


def test_response_redaction_is_recursive_and_does_not_mutate_input(client):
    payload = {
        "dhchap_key": "private",
        "items": [{"psk": "private", "host_nqn": HOST_NQN}],
        "has_dhchap_key": True,
    }
    client.request.return_value = APIResponse(200, payload)
    result = nvmeof_gateway.gateway_info(client)
    assert result.data == {
        "items": [{"host_nqn": HOST_NQN}],
        "has_dhchap_key": True,
    }
    assert payload["dhchap_key"] == "private"
    assert payload["items"][0]["psk"] == "private"


@pytest.mark.parametrize(
    "value",
    ["", "nqn", "nqn.", "NQN.2026-09.io.example:x", "nqn.bad value", 1],
)
def test_nqn_validation(value):
    with pytest.raises(ConfigurationError, match="qualified name"):
        nvmeof.nqn(value)


def test_ipv6_listener_path_is_percent_encoded(client):
    nvmeof_subsystem.listener_delete(
        client,
        NQN,
        "gw1",
        "2001:db8::10",
        4420,
        adrfam=1,
        confirm=True,
    )
    assert client.request.call_args.args[1].endswith("/gw1/2001%3Adb8%3A%3A10/4420")


def test_real_execution_loader_discovers_dynamic_operations(minion_opts, monkeypatch):
    minion_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    requests = []

    def request(_client, method, path, **kwargs):
        requests.append((method, path, kwargs))
        return APIResponse(200, {"version": "1.2.3"})

    monkeypatch.setattr(CephClient, "request", request)
    context = {}
    loader = salt.loader.minion_mods(minion_opts, context=context)
    assert loader["ceph_nvmeof.gateway_version"]()["data"] == {"version": "1.2.3"}
    assert "ceph_nvmeof.namespace_set_qos" in loader
    assert requests == [("GET", "/api/nvmeof/gateway/version", {"api_version": "1.0"})]
    ceph_utils.clear_cache(context, profile=None)


def test_real_salt_ssh_loader_uses_controller_profile(master_opts, monkeypatch):
    master_opts["ceph"] = {
        "profiles": {"default": {"url": "https://ceph.example", "token": "secret"}}
    }
    master_opts["pillar"] = {
        "ceph": {"profiles": {"default": {"url": "https://untrusted.example"}}}
    }
    urls = []

    def request(client, method, path, **kwargs):
        urls.append(client.config.url)
        assert method == "GET"
        assert path == f"/api/nvmeof/subsystem/{nvmeof.encoded(NQN)}/connection"
        assert kwargs == {"api_version": "1.0"}
        return APIResponse(200, [])

    monkeypatch.setattr(CephClient, "request", request)
    loader = salt.loader.ssh_wrapper(master_opts, context={})
    assert loader["ceph_nvmeof.connection_list"](NQN)["data"] == []
    assert urls == ["https://ceph.example"]
    loader["ceph.clear_cache"](profile=None)
