"""OSD controller operations and validation."""

import inspect
import math
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_osd as execution
from saltext.ceph.utils.ceph import osd
from saltext.ceph.utils.ceph import osd_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.wrapper import ceph_osd as wrapper


@pytest.fixture
def client():
    client = Mock()
    client.request.return_value = APIResponse(200, None)
    return client


def test_wrapper_exports_execution_functions_with_matching_signatures():
    names = {
        name
        for name, function in inspect.getmembers(execution, inspect.isfunction)
        if not name.startswith("_")
    }
    assert names == {
        name
        for name, function in inspect.getmembers(wrapper, inspect.isfunction)
        if not name.startswith("_")
    }
    for name in names:
        assert inspect.signature(getattr(wrapper, name)) == inspect.signature(
            getattr(execution, name)
        )


def test_flag_setters_preserve_the_flags_keyword_across_public_layers():
    """Keep the Salt and Python call contracts aligned with Ceph's ``flags`` field."""
    for function in (
        execution.set_flags,
        execution.set_individual_flags,
        wrapper.set_flags,
        wrapper.set_individual_flags,
        osd.set_flags,
        osd.set_individual_flags,
        osd_api.set_flags,
        osd_api.set_individual_flags,
    ):
        assert "flags" in inspect.signature(function).parameters


def test_execution_functions_document_bash_cli_examples():
    names = (
        "list_",
        "get",
        "settings",
        "smart",
        "histogram",
        "devices",
        "set_device_class",
        "create",
        "remove",
        "scrub",
        "mark",
        "reweight",
        "purge",
        "destroy",
        "safe_to_destroy",
        "safe_to_delete",
        "flags",
        "set_flags",
        "individual_flags",
        "set_individual_flags",
    )
    for name in names:
        docstring = getattr(execution, name).__doc__
        assert "CLI Example:" in docstring
        assert ".. code-block:: bash" in docstring


def test_list_requests_every_osd_with_version_1_1(client):
    client.request.return_value = APIResponse(200, [{"id": 0}], {"x-total-count": "1"})
    result = osd.list_(client)
    assert result.data == [{"id": 0}]
    assert result.headers == {"x-total-count": "1"}
    client.request.assert_called_once_with(
        "GET",
        "/api/osd",
        api_version="1.1",
        params={"offset": 0, "limit": -1, "search": "", "sort": "+id"},
    )


def test_list_passes_valid_pagination(client):
    client.request.return_value = APIResponse(200, [])
    osd.list_(client, offset=10, limit=5, search="1", sort="-id")
    assert client.request.call_args.kwargs["params"] == {
        "offset": 10,
        "limit": 5,
        "search": "1",
        "sort": "-id",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"offset": -1},
        {"offset": True},
        {"limit": -2},
        {"search": "bad\nsearch"},
        {"sort": "host"},
    ],
)
def test_list_rejects_invalid_filters(client, kwargs):
    with pytest.raises(ConfigurationError):
        osd.list_(client, **kwargs)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "function,suffix,payload,version",
    [
        (osd.get, "", {"osd_map": {}}, "1.0"),
        (osd.smart, "/smart", {}, "1.0"),
        (osd.histogram, "/histogram", {}, "1.0"),
    ],
)
def test_mapping_reads_use_expected_resource(client, function, suffix, payload, version):
    client.request.return_value = APIResponse(200, payload)
    function(client, "7")
    client.request.assert_called_once_with("GET", f"/api/osd/7{suffix}", api_version=version)


def test_settings_uses_experimental_api(client):
    client.request.return_value = APIResponse(200, {"nearfull_ratio": 0.85, "full_ratio": 0.95})
    osd.settings(client)
    client.request.assert_called_once_with("GET", "/api/osd/settings", api_version="0.1")


def test_devices_requires_a_mapping_list_response(client):
    client.request.return_value = APIResponse(200, [{"devid": "dev-1"}])
    assert osd.devices(client, 0).data == [{"devid": "dev-1"}]


def test_set_device_class_supports_setting_and_clearing(client):
    osd.set_device_class(client, 1, "nvme")
    assert client.request.call_args.kwargs["data"] == {"device_class": "nvme"}
    client.reset_mock()
    osd.set_device_class(client, 1, "")
    assert client.request.call_args.kwargs["data"] == {"device_class": ""}


def test_create_drive_groups_copies_nested_json(client):
    spec = [{"service_type": "osd", "placement": {"hosts": ("node1",)}}]
    osd.create(client, "DRIVE_GROUPS", spec, "osd-plan-1", confirm=True)
    expected = {
        "method": "drive_groups",
        "data": [{"service_type": "osd", "placement": {"hosts": ["node1"]}}],
        "tracking_id": "osd-plan-1",
    }
    client.request.assert_called_once_with("POST", "/api/osd", api_version="1.0", data=expected)
    spec[0]["placement"]["hosts"] = []
    assert client.request.call_args.kwargs["data"] == expected


def test_create_bare_normalizes_id_and_uuid(client):
    osd.create(
        client,
        "bare",
        {"svc_id": "5", "uuid": "F860CA2E-757D-48CE-B74A-87052CAD563F"},
        "bare-5",
        confirm=True,
    )
    assert client.request.call_args.kwargs["data"] == {
        "method": "bare",
        "data": {
            "svc_id": 5,
            "uuid": "f860ca2e-757d-48ce-b74a-87052cad563f",
        },
        "tracking_id": "bare-5",
    }


@pytest.mark.parametrize(
    "data",
    [
        [{"option": "cost_capacity", "encrypted": False}],
        [{"option": "throughput_optimized", "encrypted": True}],
        [{"option": "iops_optimized", "encrypted": False}],
    ],
)
def test_create_accepts_predefined_options(client, data):
    osd.create(client, "predefined", data, "predefined", confirm=True)
    assert client.request.call_args.kwargs["data"]["data"] == data
    client.reset_mock()


@pytest.mark.parametrize(
    "args",
    [
        ("drive_groups", [{}], "plan", False),
        ("other", [{}], "plan", True),
        ("drive_groups", {}, "plan", True),
        ("drive_groups", [object()], "plan", True),
        ("predefined", [{"option": "unknown", "encrypted": False}], "plan", True),
        ("predefined", [{"option": "cost_capacity"}], "plan", True),
        ("bare", {"svc_id": 1}, "bare", True),
        ("bare", {"svc_id": 1, "uuid": "bad"}, "bare", True),
        ("bare", {"svc_id": 1, "uuid": "f860ca2e-757d-48ce-b74a-87052cad563f"}, "", True),
    ],
)
def test_create_rejects_unsafe_or_invalid_requests(client, args):
    with pytest.raises(ConfigurationError):
        osd.create(client, *args)
    client.request.assert_not_called()


def test_remove_sends_explicit_safe_defaults(client):
    osd.remove(client, "7", confirm=True)
    client.request.assert_called_once_with(
        "DELETE",
        "/api/osd/7",
        api_version="1.0",
        params={"preserve_id": False, "force": False},
    )


def test_remove_can_request_replace_and_force(client):
    osd.remove(client, 7, preserve_id=True, force=True, confirm=True)
    assert client.request.call_args.kwargs["params"] == {
        "preserve_id": True,
        "force": True,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"confirm": "yes"},
        {"confirm": True, "force": "yes"},
        {"confirm": True, "preserve_id": 1},
    ],
)
def test_remove_requires_boolean_confirmation_and_options(client, kwargs):
    with pytest.raises(ConfigurationError):
        osd.remove(client, 7, **kwargs)
    client.request.assert_not_called()


@pytest.mark.parametrize("deep", [False, True])
def test_scrub_sends_explicit_depth(client, deep):
    osd.scrub(client, 2, deep)
    client.request.assert_called_once_with(
        "POST",
        "/api/osd/2/scrub",
        api_version="1.0",
        data={"deep": deep},
    )
    client.reset_mock()


@pytest.mark.parametrize("action", ["OUT", "in", "down"])
def test_mark_accepts_reversible_controller_actions(client, action):
    osd.mark(client, 3, action)
    assert client.request.call_args.kwargs["data"] == {"action": action.lower()}
    client.reset_mock()


def test_mark_lost_requires_confirmation(client):
    with pytest.raises(ConfigurationError):
        osd.mark(client, 3, "lost")
    client.request.assert_not_called()
    osd.mark(client, 3, "LOST", confirm=True)
    assert client.request.call_args.kwargs["data"] == {"action": "lost"}


@pytest.mark.parametrize("weight", [0, 0.5, 1])
def test_reweight_accepts_unit_interval(client, weight):
    osd.reweight(client, 4, weight)
    assert client.request.call_args.kwargs["data"] == {"weight": float(weight)}
    client.reset_mock()


@pytest.mark.parametrize("weight", [-0.1, 1.1, True, "0.5", math.nan, math.inf])
def test_reweight_rejects_invalid_weight(client, weight):
    with pytest.raises(ConfigurationError):
        osd.reweight(client, 4, weight)
    client.request.assert_not_called()


@pytest.mark.parametrize("function,suffix", [(osd.purge, "purge"), (osd.destroy, "destroy")])
def test_irreversible_actions_require_confirmation(client, function, suffix):
    with pytest.raises(ConfigurationError):
        function(client, 5)
    client.request.assert_not_called()
    function(client, 5, confirm=True)
    client.request.assert_called_once_with(
        "POST", f"/api/osd/5/{suffix}", api_version="1.0", data={}
    )


def test_safe_to_destroy_serializes_one_id_as_json_number(client):
    client.request.return_value = APIResponse(200, {"is_safe_to_destroy": True})
    osd.safe_to_destroy(client, "7")
    assert client.request.call_args.kwargs["params"] == {"ids": "7"}


def test_safe_to_destroy_serializes_many_ids_as_compact_json(client):
    client.request.return_value = APIResponse(200, {"is_safe_to_destroy": True})
    osd.safe_to_destroy(client, [1, "2"])
    assert client.request.call_args.kwargs["params"] == {"ids": "[1,2]"}


def test_safe_to_delete_uses_scalar_or_repeated_query_values(client):
    client.request.return_value = APIResponse(200, {"is_safe_to_delete": True})
    osd.safe_to_delete(client, 1)
    assert client.request.call_args.kwargs["params"] == {"svc_ids": "1"}
    client.reset_mock()
    osd.safe_to_delete(client, [1, 2])
    assert client.request.call_args.kwargs["params"] == {"svc_ids": ["1", "2"]}


def test_flags_read_and_replace_complete_list(client):
    client.request.return_value = APIResponse(200, ["noout", "sortbitwise"])
    assert osd.flags(client).data == ["noout", "sortbitwise"]
    client.request.assert_called_once_with("GET", "/api/osd/flags", api_version="1.0")
    client.reset_mock()
    osd.set_flags(client, ["sortbitwise", "noout"])
    client.request.assert_called_once_with(
        "PUT",
        "/api/osd/flags",
        api_version="1.0",
        data={"flags": ["sortbitwise", "noout"]},
    )


def test_individual_flags_read_and_update(client):
    client.request.return_value = APIResponse(200, [{"osd": 1, "flags": ["up"]}])
    assert osd.individual_flags(client).data[0]["osd"] == 1
    client.reset_mock()
    client.request.return_value = APIResponse(
        200, {"added": ["noout"], "removed": ["noup"], "ids": [1, 2]}
    )
    result = osd.set_individual_flags(
        client, {"noout": True, "noup": False, "noin": None}, [1, "2"]
    )
    assert result.data["ids"] == [1, 2]
    client.request.assert_called_once_with(
        "PUT",
        "/api/osd/flags/individual",
        api_version="1.0",
        data={
            "flags": {"noout": True, "noup": False, "noin": None},
            "ids": [1, 2],
        },
    )


@pytest.mark.parametrize(
    "call,args",
    [
        (osd.get, (-1,)),
        (osd.get, (True,)),
        (osd.set_device_class, (1, "bad/class")),
        (osd.scrub, (1, "true")),
        (osd.mark, (1, "other")),
        (osd.safe_to_destroy, ([],)),
        (osd.safe_to_delete, ([1, 1],)),
        (osd.set_flags, ([],)),
        (osd.set_flags, (["bad flag"],)),
        (osd.set_individual_flags, ({"pause": True}, [1])),
        (osd.set_individual_flags, ({"noout": "true"}, [1])),
        (osd.set_individual_flags, ({"noout": True}, [])),
    ],
)
def test_operations_reject_invalid_input_before_http(client, call, args):
    with pytest.raises(ConfigurationError):
        call(client, *args)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "call,payload",
    [
        (osd.list_, {}),
        (lambda client: osd.get(client, 1), []),
        (osd.settings, []),
        (lambda client: osd.smart(client, 1), []),
        (lambda client: osd.histogram(client, 1), []),
        (lambda client: osd.devices(client, 1), {}),
        (osd.flags, {}),
        (osd.individual_flags, {}),
        (lambda client: osd.safe_to_destroy(client, 1), []),
        (lambda client: osd.safe_to_delete(client, 1), []),
    ],
)
def test_reads_reject_invalid_response_shapes(client, call, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        call(client)
