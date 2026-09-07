"""Shared state reconciliation helpers."""

from unittest.mock import Mock

import pytest

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError


def test_state_result_has_standard_salt_shape():
    assert reconcile.state_result("resource") == {
        "name": "resource",
        "changes": {},
        "result": False,
        "comment": "",
    }


def test_envelope_detaches_headers_and_validates_success_status():
    headers = {"x-total-count": "1"}
    result = reconcile.envelope({"status": 200, "data": [], "headers": headers})
    headers.clear()
    assert result["headers"] == {"x-total-count": "1"}


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"status": True},
        {"status": 199},
        {"status": 300},
        {"status": 200, "headers": []},
    ],
)
def test_envelope_rejects_invalid_values(value):
    with pytest.raises(ProtocolError):
        reconcile.envelope(value)


def test_data_enforces_expected_shape():
    assert reconcile.data({"status": 200, "data": []}, expected=list) == []
    with pytest.raises(ProtocolError):
        reconcile.data({"status": 200, "data": {}}, expected=list)


def test_wait_if_accepted_passes_through_sync_response():
    response = {"status": 204, "data": None, "headers": {}}
    assert reconcile.wait_if_accepted({}, response) == response


def test_wait_if_accepted_calls_task_waiter_with_reference():
    waiter = Mock(return_value={"status": 200, "data": {"success": True}, "headers": {}})
    response = {
        "status": 202,
        "data": {"name": "service/create", "metadata": {"service_name": "rgw.site"}},
        "headers": {},
    }
    result = reconcile.wait_if_accepted(
        {"ceph_task.wait": waiter},
        response,
        profile="prod",
        timeout=600,
        interval=3,
    )
    assert result["data"]["success"] is True
    waiter.assert_called_once_with(
        "service/create",
        metadata={"service_name": "rgw.site"},
        timeout=600,
        interval=3,
        fail_on_error=True,
        profile="prod",
    )


@pytest.mark.parametrize(
    "response,salt,error",
    [
        ({"status": 202, "data": None}, {}, ProtocolError),
        ({"status": 202, "data": {"name": "x", "metadata": []}}, {}, ProtocolError),
        (
            {"status": 202, "data": {"name": "x", "metadata": {}}},
            {},
            ConfigurationError,
        ),
    ],
)
def test_wait_if_accepted_rejects_invalid_or_unsupported_tasks(response, salt, error):
    with pytest.raises(error):
        reconcile.wait_if_accepted(salt, response)


def test_project_compares_only_managed_nested_fields():
    current = {"name": "x", "placement": {"count": 2, "hosts": ["a"]}, "status": {}}
    desired = {"name": "x", "placement": {"count": 2}}
    assert reconcile.project(current, desired) == desired


def test_state_outcome_helpers_mutate_standard_return():
    ret = reconcile.state_result("x")
    assert reconcile.no_change(ret, "ok")["result"] is True
    ret = reconcile.state_result("x")
    assert reconcile.planned(ret, 1, 2, "plan")["result"] is None
    ret = reconcile.state_result("x")
    assert reconcile.changed(ret, 1, 2, "done")["changes"] == {"old": 1, "new": 2}
    ret = reconcile.state_result("x")
    assert reconcile.failed(ret, ConfigurationError("safe"))["comment"] == "safe"
