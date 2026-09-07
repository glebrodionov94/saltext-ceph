"""Declarative current-only NVMe-oF state contracts."""

from unittest.mock import Mock

import pytest
import salt.loader
from salt.exceptions import CommandExecutionError

from saltext.ceph.states import ceph_nvmeof as state

NQN = "nqn.2026-09.io.example:storage"
HOST_NQN = "nqn.2026-09.io.example:host1"


def envelope(data=None, status=200):
    return {"status": status, "data": data, "headers": {}}


def task(name="nvmeof/task"):
    return envelope({"name": name, "metadata": {"nqn": NQN}}, status=202)


def missing():
    return CommandExecutionError("missing", info={"status": 404})


def subsystem(**changes):
    result = {
        "nqn": NQN,
        "serial_number": "SN-1",
        "model_number": "Ceph bdev Controller",
        "max_namespaces": 128,
        "namespace_count": 0,
        "has_dhchap_key": False,
        "network_mask": [],
    }
    result.update(changes)
    return result


def listener(**changes):
    result = {
        "host_name": "gw1",
        "trtype": "TCP",
        "adrfam": 0,
        "traddr": "192.0.2.10",
        "trsvcid": 4420,
        "secure": False,
        "active": True,
        "manual": True,
    }
    result.update(changes)
    return result


def host(**changes):
    result = {
        "nqn": HOST_NQN,
        "use_psk": False,
        "use_dhchap": False,
        "dhchap_controller_origin": "No Key",
        "disconnected_due_to_keepalive_timeout": False,
    }
    result.update(changes)
    return result


def namespace(**changes):
    result = {
        "nsid": 1,
        "ns_subsystem_nqn": NQN,
        "rbd_image_name": "vm-1",
        "rbd_pool_name": "rbd",
        "rbd_data_pool_name": None,
        "rados_namespace_name": None,
        "rbd_image_size": 1024,
        "block_size": 512,
        "load_balancing_group": 1,
        "rw_ios_per_second": 0,
        "rw_mbytes_per_second": 0,
        "r_mbytes_per_second": 0,
        "w_mbytes_per_second": 0,
        "auto_visible": True,
        "hosts": [],
        "uuid": "1d5dd9a9-2ba8-42f2-a732-605c8e73afcf",
        "trash_image": False,
        "disable_auto_resize": False,
        "read_only": False,
        "location": None,
        "encryption_entries": [],
        "degraded": False,
        "pinned": False,
    }
    result.update(changes)
    return result


@pytest.fixture(autouse=True)
def loader_globals(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": False}, raising=False)
    monkeypatch.setattr(state, "__salt__", {}, raising=False)


def source(tmp_path, name="key", value="private-value"):
    path = tmp_path / name
    path.write_text(value + "\n", encoding="utf-8")
    return str(path)


def test_virtual_requires_the_get_and_mutation_surface(monkeypatch):
    result = state.__virtual__()
    assert result[0] is False
    assert "subsystem_get" in result[1]
    required = {
        name: Mock() for name in result[1].removeprefix("Missing execution functions: ").split(", ")
    }
    monkeypatch.setattr(state, "__salt__", required)
    assert state.__virtual__() == "ceph_nvmeof"


def test_gateway_configured_noop_uses_exact_safe_projection(monkeypatch):
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.gateway_log_level": Mock(
                return_value=envelope({"log_level": "WARNING", "token": "private"})
            ),
            "ceph_nvmeof.gateway_info": Mock(
                return_value=envelope({"io_stats_enabled": True, "psk": "private"})
            ),
        },
    )
    result = state.gateway_configured(
        "gateway-one",
        log_level="warning",
        io_stats_enabled=True,
        server_address="gw1.example",
    )
    assert result["result"] is True
    assert not result["changes"]
    assert "private" not in repr(result)


def test_gateway_configured_updates_waits_and_post_reads(monkeypatch):
    set_log = Mock(return_value=task("nvmeof/gateway/log"))
    set_stats = Mock(return_value=envelope(status=200))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.gateway_log_level": Mock(
                side_effect=[
                    envelope({"log_level": "info"}),
                    envelope({"log_level": "debug"}),
                ]
            ),
            "ceph_nvmeof.gateway_info": Mock(
                side_effect=[
                    envelope({"io_stats_enabled": False}),
                    envelope({"io_stats_enabled": True}),
                ]
            ),
            "ceph_nvmeof.gateway_set_log_level": set_log,
            "ceph_nvmeof.gateway_set_io_stats": set_stats,
            "ceph_task.wait": wait,
        },
    )
    result = state.gateway_configured(
        "gateway-one",
        log_level="DEBUG",
        io_stats_enabled=True,
        gw_group="alpha",
        server_address="gw1.example",
    )
    assert result["result"] is True
    assert result["changes"] == {
        "old": {"log_level": "info", "io_stats_enabled": False},
        "new": {"log_level": "debug", "io_stats_enabled": True},
    }
    set_log.assert_called_once_with(
        "debug",
        profile="default",
        gw_group="alpha",
        server_address="gw1.example",
    )
    set_stats.assert_called_once_with(
        True,
        profile="default",
        gw_group="alpha",
        server_address="gw1.example",
    )
    wait.assert_called_once()


def test_gateway_configured_requires_address_and_declared_setting(monkeypatch):
    get = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_nvmeof.gateway_info": get})
    assert "required" in state.gateway_configured("gateway-one", io_stats_enabled=True)["comment"]
    result = state.gateway_configured("gateway-one", server_address="gw1.example")
    assert result["result"] is False
    assert "At least one" in result["comment"]
    get.assert_not_called()


def test_subsystem_present_noop_projects_only_declared_get_fields(monkeypatch):
    get = Mock(
        return_value=envelope(
            subsystem(
                response_token="server-private",
                dhchap_key="must-never-escape",
            )
        )
    )
    monkeypatch.setattr(state, "__salt__", {"ceph_nvmeof.subsystem_get": get})
    result = state.subsystem_present(
        NQN,
        serial_number="SN-1",
        model_name="Ceph bdev Controller",
        max_namespaces=128,
        network_mask=[],
    )
    assert result["result"] is True
    assert not result["changes"]
    assert "private" not in repr(result)


def test_subsystem_create_validates_source_in_test_mode_without_disclosure(tmp_path, monkeypatch):
    missing_source = str(tmp_path / "missing-secret")
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.subsystem_get": Mock(side_effect=missing())},
    )
    result = state.subsystem_present(NQN, dhchap_key_source=missing_source)
    assert result["result"] is False
    assert missing_source not in result["comment"]
    assert "dhchap" not in repr(result["changes"]).lower()


def test_subsystem_create_waits_for_202_and_post_reads(tmp_path, monkeypatch):
    key_source = source(tmp_path, "subsystem-key")
    get = Mock(side_effect=[missing(), envelope(subsystem(has_dhchap_key=True))])
    create = Mock(return_value=task("nvmeof/subsystem/create"))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.subsystem_get": get,
            "ceph_nvmeof.subsystem_create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.subsystem_present(NQN, dhchap_key_source=key_source)
    assert result["result"] is True
    assert "private-value" not in repr(result)
    assert key_source not in repr(result)
    assert result["changes"]["new"] == {"nqn": NQN, "has_dhchap_key": True}
    assert create.call_args.kwargs["dhchap_key_source"] == key_source
    wait.assert_called_once()


def test_subsystem_missing_key_requires_confirm_then_installs_from_source(tmp_path, monkeypatch):
    key_source = source(tmp_path)
    change = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.subsystem_get": Mock(return_value=envelope(subsystem())),
            "ceph_nvmeof.subsystem_change_key": change,
        },
    )
    result = state.subsystem_present(NQN, dhchap_key_source=key_source)
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    change.assert_not_called()

    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.subsystem_get": Mock(
                side_effect=[
                    envelope(subsystem()),
                    envelope(subsystem(has_dhchap_key=True)),
                ]
            ),
            "ceph_nvmeof.subsystem_change_key": change,
        },
    )
    assert (
        state.subsystem_present(NQN, dhchap_key_source=key_source, confirm=True)["result"] is True
    )
    change.assert_called_once_with(
        NQN,
        key_source,
        confirm=True,
        profile="default",
    )


def test_subsystem_create_only_drift_requires_empty_confirmed_replacement(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=201))
    before = subsystem(serial_number="old")
    after = subsystem(serial_number="new")
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.subsystem_get": Mock(return_value=envelope(before))},
    )
    result = state.subsystem_present(NQN, serial_number="new")
    assert result["result"] is False
    assert "confirm_replace=True" in result["comment"]

    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.subsystem_get": Mock(
                side_effect=[envelope(before), missing(), envelope(after)]
            ),
            "ceph_nvmeof.subsystem_delete": delete,
            "ceph_nvmeof.subsystem_create": create,
        },
    )
    result = state.subsystem_present(NQN, serial_number="new", confirm_replace=True)
    assert result["result"] is True
    delete.assert_called_once_with(
        NQN,
        force=False,
        confirm=True,
        profile="default",
    )
    create.assert_called_once()


def test_subsystem_replacement_refuses_nonempty_resource(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.subsystem_get": Mock(
                return_value=envelope(subsystem(serial_number="old", namespace_count=1))
            ),
            "ceph_nvmeof.subsystem_delete": delete,
        },
    )
    result = state.subsystem_present(NQN, serial_number="new", confirm_replace=True)
    assert result["result"] is False
    assert "with namespaces" in result["comment"]
    delete.assert_not_called()


def test_subsystem_replacement_refuses_to_drop_an_unmanaged_key(monkeypatch):
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.subsystem_get": Mock(
                return_value=envelope(subsystem(serial_number="old", has_dhchap_key=True))
            ),
            "ceph_nvmeof.subsystem_delete": delete,
        },
    )
    result = state.subsystem_present(NQN, serial_number="new", confirm_replace=True)
    assert result["result"] is False
    assert "preserve the subsystem key" in result["comment"]
    delete.assert_not_called()


def test_subsystem_absent_test_mode_and_confirmed_post_read(monkeypatch):
    delete = Mock(return_value=task("nvmeof/subsystem/delete"))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.subsystem_get": Mock(return_value=envelope(subsystem()))},
    )
    assert state.subsystem_absent(NQN)["result"] is None

    monkeypatch.setattr(state, "__opts__", {"test": False})
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.subsystem_get": Mock(side_effect=[envelope(subsystem()), missing()]),
            "ceph_nvmeof.subsystem_delete": delete,
            "ceph_task.wait": wait,
        },
    )
    result = state.subsystem_absent(NQN, force=True, confirm=True)
    assert result["result"] is True
    assert result["changes"]["new"] is None
    delete.assert_called_once_with(
        NQN,
        force=True,
        confirm=True,
        profile="default",
    )
    wait.assert_called_once()


def test_listener_present_noop_and_create(monkeypatch):
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.listener_list": Mock(return_value=envelope([listener()]))},
    )
    assert state.listener_present(NQN, "gw1", "192.0.2.10")["result"] is True

    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.listener_list": Mock(
                side_effect=[envelope([]), envelope([listener(secure=True)])]
            ),
            "ceph_nvmeof.listener_create": create,
        },
    )
    result = state.listener_present(NQN, "gw1", "192.0.2.10", secure=True)
    assert result["result"] is True
    create.assert_called_once_with(
        NQN,
        "gw1",
        "192.0.2.10",
        trsvcid=4420,
        adrfam=0,
        secure=True,
        profile="default",
    )


def test_listener_drift_requires_confirmed_delete_create(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.listener_list": Mock(return_value=envelope([listener()]))},
    )
    result = state.listener_present(NQN, "gw1", "192.0.2.10", secure=True)
    assert result["result"] is False
    assert "confirm_replace=True" in result["comment"]

    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.listener_list": Mock(
                side_effect=[
                    envelope([listener()]),
                    envelope([]),
                    envelope([listener(secure=True)]),
                ]
            ),
            "ceph_nvmeof.listener_delete": delete,
            "ceph_nvmeof.listener_create": create,
        },
    )
    result = state.listener_present(
        NQN,
        "gw1",
        "192.0.2.10",
        secure=True,
        confirm_replace=True,
    )
    assert result["result"] is True
    delete.assert_called_once()
    create.assert_called_once()


def test_listener_absent_requires_confirm_and_verifies(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.listener_list": Mock(return_value=envelope([listener()])),
            "ceph_nvmeof.listener_delete": delete,
        },
    )
    assert state.listener_absent(NQN, "gw1", "192.0.2.10")["result"] is False
    delete.assert_not_called()

    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.listener_list": Mock(side_effect=[envelope([listener()]), envelope([])]),
            "ceph_nvmeof.listener_delete": delete,
        },
    )
    assert (
        state.listener_absent(
            NQN,
            "gw1",
            "192.0.2.10",
            force=True,
            confirm=True,
        )["result"]
        is True
    )


def test_listener_rejects_duplicate_or_malformed_get_data(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.listener_list": Mock(return_value=envelope([listener(), listener()])),
            "ceph_nvmeof.listener_create": create,
        },
    )
    result = state.listener_present(NQN, "gw1", "192.0.2.10")
    assert result["result"] is False
    assert "duplicate" in result["comment"]
    create.assert_not_called()


def test_host_present_noop_redacts_unexpected_server_secrets(monkeypatch):
    current = host(
        use_dhchap=True,
        dhchap_key="server-private",
        psk="also-private",
    )
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.host_list": Mock(return_value=envelope([current]))},
    )
    result = state.host_present(HOST_NQN, NQN)
    assert result["result"] is True
    assert "private" not in repr(result)


def test_host_create_uses_sources_but_never_emits_them(tmp_path, monkeypatch):
    dhchap = source(tmp_path, "dhchap")
    controller = source(tmp_path, "controller")
    psk = source(tmp_path, "psk")
    after = host(
        use_dhchap=True,
        use_psk=True,
        dhchap_controller_origin="Host Specific",
    )
    create = Mock(return_value=task("nvmeof/host/create"))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.host_list": Mock(side_effect=[envelope([]), envelope([after])]),
            "ceph_nvmeof.host_create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.host_present(
        HOST_NQN,
        NQN,
        dhchap_key_source=dhchap,
        dhchap_controller_key_source=controller,
        psk_source=psk,
    )
    assert result["result"] is True
    assert "private-value" not in repr(result)
    assert dhchap not in repr(result)
    assert controller not in repr(result)
    assert psk not in repr(result)
    assert result["changes"]["new"] == {
        "nqn": HOST_NQN,
        "use_dhchap": True,
        "dhchap_controller_origin": "Host Specific",
        "use_psk": True,
    }
    wait.assert_called_once()


def test_host_installs_missing_dhchap_keys_only_after_confirm(tmp_path, monkeypatch):
    dhchap = source(tmp_path, "dhchap")
    controller = source(tmp_path, "controller")
    change_key = Mock(return_value=envelope(status=200))
    change_controller = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.host_list": Mock(return_value=envelope([host()]))},
    )
    result = state.host_present(
        HOST_NQN,
        NQN,
        dhchap_key_source=dhchap,
        dhchap_controller_key_source=controller,
    )
    assert result["result"] is False
    assert "confirm=True" in result["comment"]

    after = host(use_dhchap=True, dhchap_controller_origin="Host Specific")
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.host_list": Mock(side_effect=[envelope([host()]), envelope([after])]),
            "ceph_nvmeof.host_change_key": change_key,
            "ceph_nvmeof.host_change_controller_key": change_controller,
        },
    )
    result = state.host_present(
        HOST_NQN,
        NQN,
        dhchap_key_source=dhchap,
        dhchap_controller_key_source=controller,
        confirm=True,
    )
    assert result["result"] is True
    change_key.assert_called_once()
    change_controller.assert_called_once()


def test_host_missing_psk_requires_safe_confirmed_replacement(tmp_path, monkeypatch):
    psk = source(tmp_path, "psk")
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.host_list": Mock(return_value=envelope([host()]))},
    )
    result = state.host_present(HOST_NQN, NQN, psk_source=psk)
    assert result["result"] is False
    assert "confirm_replace=True" in result["comment"]

    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.host_list": Mock(
                side_effect=[envelope([host()]), envelope([]), envelope([host(use_psk=True)])]
            ),
            "ceph_nvmeof.host_delete": delete,
            "ceph_nvmeof.host_create": create,
        },
    )
    result = state.host_present(HOST_NQN, NQN, psk_source=psk, confirm_replace=True)
    assert result["result"] is True
    delete.assert_called_once()
    create.assert_called_once()


def test_host_psk_replacement_refuses_to_drop_unmanaged_dhchap(tmp_path, monkeypatch):
    psk = source(tmp_path, "psk")
    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.host_list": Mock(return_value=envelope([host(use_dhchap=True)])),
            "ceph_nvmeof.host_delete": delete,
        },
    )
    result = state.host_present(
        HOST_NQN,
        NQN,
        psk_source=psk,
        confirm_replace=True,
    )
    assert result["result"] is False
    assert "preserve" in result["comment"]
    delete.assert_not_called()


def test_host_prevalidates_all_needed_sources_before_first_key_change(tmp_path, monkeypatch):
    dhchap = source(tmp_path, "dhchap")
    missing_controller = str(tmp_path / "missing-controller")
    change_key = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.host_list": Mock(return_value=envelope([host()])),
            "ceph_nvmeof.host_change_key": change_key,
        },
    )
    result = state.host_present(
        HOST_NQN,
        NQN,
        dhchap_key_source=dhchap,
        dhchap_controller_key_source=missing_controller,
        confirm=True,
    )
    assert result["result"] is False
    assert missing_controller not in result["comment"]
    change_key.assert_not_called()


def test_host_absent_confirmation_and_post_read(monkeypatch):
    delete = Mock(return_value=envelope(status=204))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.host_list": Mock(side_effect=[envelope([host()]), envelope([])]),
            "ceph_nvmeof.host_delete": delete,
        },
    )
    result = state.host_absent(HOST_NQN, NQN, confirm=True)
    assert result["result"] is True
    assert result["changes"]["new"] is None
    delete.assert_called_once_with(
        NQN,
        HOST_NQN,
        force=False,
        keep_connections=False,
        confirm=True,
        profile="default",
    )


def test_wildcard_host_rejects_secret_sources_before_read(tmp_path, monkeypatch):
    list_ = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_nvmeof.host_list": list_})
    result = state.host_present("*", NQN, psk_source=source(tmp_path))
    assert result["result"] is False
    assert "cannot carry" in result["comment"]
    list_.assert_not_called()


def test_namespace_present_noop_uses_exact_declared_projection(monkeypatch):
    current = namespace(psk="server-private", response_token="also-private")
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.namespace_get": Mock(return_value=envelope(current))},
    )
    result = state.namespace_present("1", NQN, "vm-1")
    assert result["result"] is True
    assert not result["changes"]
    assert "private" not in repr(result)


def test_namespace_create_requires_size_for_new_image_before_read(monkeypatch):
    get = Mock()
    monkeypatch.setattr(state, "__salt__", {"ceph_nvmeof.namespace_get": get})
    result = state.namespace_present("1", NQN, "vm-1", create_image=True)
    assert result["result"] is False
    assert "requires rbd_image_size" in result["comment"]
    get.assert_not_called()


def test_namespace_create_waits_and_post_reads(monkeypatch):
    create = Mock(return_value=task("nvmeof/namespace/create"))
    wait = Mock(return_value=envelope({"success": True}))
    get = Mock(side_effect=[missing(), envelope(namespace(rbd_image_size=2048))])
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": get,
            "ceph_nvmeof.namespace_create": create,
            "ceph_task.wait": wait,
        },
    )
    result = state.namespace_present(
        "1",
        NQN,
        "vm-1",
        create_image=True,
        rbd_image_size=2048,
    )
    assert result["result"] is True
    assert result["changes"]["old"] is None
    assert create.call_args.kwargs["create_image"] is True
    assert create.call_args.kwargs["rbd_image_size"] == 2048
    assert create.call_args.kwargs["nsid"] == 1
    wait.assert_called_once()


def test_namespace_force_create_can_preview_but_live_run_requires_confirm(monkeypatch):
    create = Mock()
    monkeypatch.setattr(state, "__opts__", {"test": True})
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.namespace_get": Mock(side_effect=missing())},
    )
    assert state.namespace_present("1", NQN, "vm-1", force_create=True)["result"] is None

    monkeypatch.setattr(state, "__opts__", {"test": False})
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(side_effect=missing()),
            "ceph_nvmeof.namespace_create": create,
        },
    )
    result = state.namespace_present("1", NQN, "vm-1", force_create=True)
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    create.assert_not_called()


def test_namespace_mutable_fields_use_actions_wait_and_final_post_read(monkeypatch):
    before = namespace()
    middle = namespace(
        rbd_image_size=2048,
        load_balancing_group=2,
        pinned=True,
        rw_ios_per_second=7,
        trash_image=True,
        auto_visible=False,
        disable_auto_resize=True,
        location="rack-a",
    )
    after = dict(middle, hosts=[HOST_NQN])
    mutations = {
        "ceph_nvmeof.namespace_resize": Mock(return_value=task("nvmeof/resize")),
        "ceph_nvmeof.namespace_change_load_balancing_group": Mock(
            return_value=envelope(status=200)
        ),
        "ceph_nvmeof.namespace_set_qos": Mock(return_value=envelope(status=200)),
        "ceph_nvmeof.namespace_set_rbd_trash_image": Mock(return_value=envelope(status=200)),
        "ceph_nvmeof.namespace_change_location": Mock(return_value=envelope(status=200)),
        "ceph_nvmeof.namespace_change_visibility": Mock(return_value=envelope(status=200)),
        "ceph_nvmeof.namespace_set_auto_resize": Mock(return_value=envelope(status=200)),
        "ceph_nvmeof.namespace_add_host": Mock(return_value=envelope(status=200)),
    }
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(
                side_effect=[envelope(before), envelope(middle), envelope(after)]
            ),
            "ceph_task.wait": wait,
            **mutations,
        },
    )
    result = state.namespace_present(
        "1",
        NQN,
        "vm-1",
        rbd_image_size=2048,
        load_balancing_group=2,
        rw_ios_per_second=7,
        trash_image=True,
        auto_visible=False,
        disable_auto_resize=True,
        location="rack-a",
        hosts=[HOST_NQN],
        confirm=True,
    )
    assert result["result"] is True
    assert result["changes"]["new"]["hosts"] == [HOST_NQN]
    assert all(call.call_count == 1 for call in mutations.values())
    wait.assert_called_once()


def test_namespace_disruptive_update_requires_confirm_without_mutating(monkeypatch):
    trash = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(return_value=envelope(namespace())),
            "ceph_nvmeof.namespace_set_rbd_trash_image": trash,
        },
    )
    result = state.namespace_present("1", NQN, "vm-1", trash_image=True)
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    trash.assert_not_called()


def test_namespace_qos_update_is_idempotent_without_forced_confirmation(monkeypatch):
    set_qos = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(
                side_effect=[
                    envelope(namespace()),
                    envelope(namespace(rw_ios_per_second=9)),
                ]
            ),
            "ceph_nvmeof.namespace_set_qos": set_qos,
        },
    )
    result = state.namespace_present("1", NQN, "vm-1", rw_ios_per_second=9)
    assert result["result"] is True
    set_qos.assert_called_once_with(
        NQN,
        1,
        force=False,
        confirm=False,
        profile="default",
        rw_ios_per_second=9,
    )


def test_namespace_host_add_does_not_need_confirmation_but_removal_does(monkeypatch):
    add = Mock(return_value=envelope(status=200))
    get = Mock(
        side_effect=[
            envelope(namespace()),
            envelope(namespace()),
            envelope(namespace(hosts=[HOST_NQN])),
        ]
    )
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.namespace_get": get, "ceph_nvmeof.namespace_add_host": add},
    )
    assert state.namespace_present("1", NQN, "vm-1", hosts=[HOST_NQN])["result"] is True
    add.assert_called_once()

    delete = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(return_value=envelope(namespace(hosts=[HOST_NQN]))),
            "ceph_nvmeof.namespace_delete_host": delete,
        },
    )
    result = state.namespace_present("1", NQN, "vm-1", hosts=[])
    assert result["result"] is False
    assert "confirm=True" in result["comment"]
    delete.assert_not_called()


def test_namespace_create_only_drift_requires_confirmed_replacement(monkeypatch):
    before = namespace(rbd_pool_name="old")
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=201))
    monkeypatch.setattr(
        state,
        "__salt__",
        {"ceph_nvmeof.namespace_get": Mock(return_value=envelope(before))},
    )
    result = state.namespace_present("1", NQN, "vm-1")
    assert result["result"] is False
    assert "confirm_replace=True" in result["comment"]

    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(
                side_effect=[
                    envelope(before),
                    missing(),
                    envelope(namespace()),
                    envelope(namespace()),
                ]
            ),
            "ceph_nvmeof.namespace_delete": delete,
            "ceph_nvmeof.namespace_create": create,
        },
    )
    result = state.namespace_present("1", NQN, "vm-1", confirm_replace=True)
    assert result["result"] is True
    delete.assert_called_once_with(
        NQN,
        1,
        force=False,
        confirm=True,
        profile="default",
    )
    create.assert_called_once()


def test_namespace_replacement_preserves_unmanaged_get_fields(monkeypatch):
    before = namespace(
        rbd_pool_name="old",
        load_balancing_group=3,
        pinned=True,
        rw_ios_per_second=11,
        hosts=[HOST_NQN],
    )
    created = namespace()
    restored_without_host = namespace(
        load_balancing_group=3,
        pinned=True,
        rw_ios_per_second=11,
    )
    restored = dict(restored_without_host, hosts=[HOST_NQN])
    delete = Mock(return_value=envelope(status=204))
    create = Mock(return_value=envelope(status=201))
    change_group = Mock(return_value=envelope(status=200))
    set_qos = Mock(return_value=envelope(status=200))
    add_host = Mock(return_value=envelope(status=200))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(
                side_effect=[
                    envelope(before),
                    missing(),
                    envelope(created),
                    envelope(restored_without_host),
                    envelope(restored),
                ]
            ),
            "ceph_nvmeof.namespace_delete": delete,
            "ceph_nvmeof.namespace_create": create,
            "ceph_nvmeof.namespace_change_load_balancing_group": change_group,
            "ceph_nvmeof.namespace_set_qos": set_qos,
            "ceph_nvmeof.namespace_add_host": add_host,
        },
    )
    result = state.namespace_present("1", NQN, "vm-1", confirm_replace=True)
    assert result["result"] is True
    assert create.call_args.kwargs["uuid"] == before["uuid"]
    assert create.call_args.kwargs["rbd_image_size"] == 1024
    assert create.call_args.kwargs["load_balancing_group"] == 3
    change_group.assert_called_once()
    set_qos.assert_called_once_with(
        NQN,
        1,
        force=False,
        confirm=False,
        profile="default",
        rw_ios_per_second=11,
    )
    add_host.assert_called_once()
    changes = result["changes"]["new"]
    assert changes["rbd_pool_name"] == "rbd"
    assert "uuid" not in changes
    assert "hosts" not in changes
    assert "pinned" not in changes
    assert "rw_ios_per_second" not in changes


def test_namespace_test_mode_reports_encryption_projection_without_mutation(monkeypatch):
    monkeypatch.setattr(state, "__opts__", {"test": True})
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(side_effect=missing()),
            "ceph_nvmeof.namespace_create": create,
        },
    )
    result = state.namespace_present(
        "1",
        NQN,
        "vm-1",
        encryption_format=["luks2"],
        key_id=["kmip-key-1"],
    )
    assert result["result"] is None
    assert result["changes"]["new"]["encryption_entries"] == [
        {"format": "LUKS2", "key_id": "kmip-key-1"}
    ]
    create.assert_not_called()


def test_namespace_absent_requires_confirm_waits_and_post_reads(monkeypatch):
    delete = Mock(return_value=task("nvmeof/namespace/delete"))
    wait = Mock(return_value=envelope({"success": True}))
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(side_effect=[envelope(namespace()), missing()]),
            "ceph_nvmeof.namespace_delete": delete,
            "ceph_task.wait": wait,
        },
    )
    result = state.namespace_absent("1", NQN, force=True, confirm=True)
    assert result["result"] is True
    assert result["changes"]["new"] is None
    delete.assert_called_once_with(
        NQN,
        1,
        force=True,
        confirm=True,
        profile="default",
    )
    wait.assert_called_once()


def test_namespace_mismatched_get_identity_fails_without_mutation(monkeypatch):
    create = Mock()
    monkeypatch.setattr(
        state,
        "__salt__",
        {
            "ceph_nvmeof.namespace_get": Mock(
                return_value=envelope(namespace(ns_subsystem_nqn="nqn.2026-09.io.example:other"))
            ),
            "ceph_nvmeof.namespace_create": create,
        },
    )
    result = state.namespace_present("1", NQN, "vm-1")
    assert result["result"] is False
    assert "did not match" in result["comment"]
    create.assert_not_called()


def test_real_salt_loader_resolves_each_nvmeof_state(minion_opts):
    missing_functions = state.__virtual__()[1].removeprefix("Missing execution functions: ")
    functions = {name: Mock() for name in missing_functions.split(", ")}
    loader = salt.loader.states(
        minion_opts,
        functions,
        salt.loader.utils(minion_opts),
        salt.loader.serializers(minion_opts),
        whitelist=["ceph_nvmeof"],
    )
    names = (
        "gateway_configured",
        "subsystem_present",
        "subsystem_absent",
        "listener_present",
        "listener_absent",
        "host_present",
        "host_absent",
        "namespace_present",
        "namespace_absent",
    )
    assert all(callable(loader[f"ceph_nvmeof.{name}"]) for name in names)
