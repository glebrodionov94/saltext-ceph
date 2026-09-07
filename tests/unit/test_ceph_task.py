"""Dashboard task operations and bounded polling."""

import inspect
from unittest.mock import Mock

import pytest

from saltext.ceph.modules import ceph_task as execution
from saltext.ceph.utils.ceph import task
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError
from saltext.ceph.utils.ceph.errors import TaskFailedError
from saltext.ceph.utils.ceph.errors import TaskTimeoutError
from saltext.ceph.wrapper import ceph_task as wrapper


@pytest.fixture
def client():
    return Mock()


def task_list(executing=None, finished=None):
    return APIResponse(
        200,
        {
            "executing_tasks": executing or [],
            "finished_tasks": finished or [],
        },
    )


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


def test_list_supports_optional_name_filter(client):
    client.request.return_value = task_list()
    task.list_(client, "service/create")
    client.request.assert_called_once_with(
        "GET", "/api/task", api_version="1.0", params={"name": "service/create"}
    )


def test_list_without_filter_sends_empty_params(client):
    client.request.return_value = task_list()
    task.list_(client)
    assert client.request.call_args.kwargs["params"] == {}


def test_list_redacts_task_details_and_nested_credentials_by_default(client):
    client.request.return_value = task_list(
        finished=[
            {
                "name": "rgw/import",
                "metadata": {
                    "realm": "lab",
                    "connection": [
                        {
                            "accessKey": "access",
                            "secret_key": "secret",
                            "dhchap_key": "dhchap",
                            "psk": "psk",
                        }
                    ],
                    "nested": {"bootstrap_token": "token", "safe": True},
                },
                "success": False,
                "exception": "password=private",
                "ret_value": {"private_key": "private"},
            }
        ]
    )

    result = task.list_(client).data["finished_tasks"][0]

    assert "exception" not in result
    assert "ret_value" not in result
    assert result["metadata"] == {
        "realm": "lab",
        "connection": [
            {
                "accessKey": "********",
                "secret_key": "********",
                "dhchap_key": "********",
                "psk": "********",
            }
        ],
        "nested": {"bootstrap_token": "********", "safe": True},
    }


def test_list_can_return_original_task_details_with_explicit_opt_in(client):
    raw = {
        "name": "rgw/import",
        "metadata": {"token": "private"},
        "success": False,
        "exception": "private failure",
        "ret_value": {"secret": "private"},
    }
    client.request.return_value = task_list(finished=[raw])

    assert task.list_(client, include_secrets=True).data["finished_tasks"][0] == raw


@pytest.mark.parametrize("value", [None, 0, 1, "true", []])
def test_list_rejects_non_boolean_include_secrets_before_request(client, value):
    with pytest.raises(ConfigurationError, match="include_secrets"):
        task.list_(client, include_secrets=value)
    client.request.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"executing_tasks": [], "finished_tasks": {}},
        {"executing_tasks": [None], "finished_tasks": []},
    ],
)
def test_list_rejects_invalid_response(client, payload):
    client.request.return_value = APIResponse(200, payload)
    with pytest.raises(ProtocolError):
        task.list_(client)


def test_wait_polls_executing_then_returns_matching_finished(client, monkeypatch):
    metadata = {"service_name": "rgw.site"}
    client.request.side_effect = [
        task_list(executing=[{"name": "service/create", "metadata": metadata}]),
        task_list(
            finished=[
                {
                    "name": "service/create",
                    "metadata": metadata,
                    "success": True,
                }
            ]
        ),
    ]
    monkeypatch.setattr(task.time, "sleep", Mock())
    result = task.wait(client, "service/create", metadata, timeout=5, interval=0.1)
    assert result.data["success"] is True
    assert client.request.call_count == 2
    task.time.sleep.assert_called_once()  # pylint: disable=no-member


def test_wait_uses_metadata_as_subset(client):
    client.request.return_value = task_list(
        finished=[
            {
                "name": "pool/create",
                "metadata": {"pool": "data", "extra": 1},
                "success": True,
            }
        ]
    )
    result = task.wait(client, "pool/create", {"pool": "data"})
    assert result.data["metadata"]["extra"] == 1


def test_wait_raises_sanitized_failure_by_default(client):
    client.request.return_value = task_list(
        finished=[
            {
                "name": "pool/delete",
                "metadata": {"pool": "data"},
                "success": False,
                "exception": "password=private",
            }
        ]
    )
    with pytest.raises(TaskFailedError) as exc:
        task.wait(client, "pool/delete", {"pool": "data"})
    assert "private" not in str(exc.value)


def test_wait_can_return_failed_task_for_observers(client):
    client.request.return_value = task_list(
        finished=[
            {
                "name": "pool/delete",
                "metadata": {"pool": "data"},
                "success": False,
            }
        ]
    )
    assert (
        task.wait(
            client,
            "pool/delete",
            {"pool": "data"},
            fail_on_error=False,
        ).data["success"]
        is False
    )


def test_wait_redacts_returned_task_after_matching_original_metadata(client):
    client.request.return_value = task_list(
        finished=[
            {
                "name": "rgw/import",
                "metadata": {"token": "match-me", "realm": "lab"},
                "success": True,
                "ret_value": {"secret": "private"},
            }
        ]
    )

    result = task.wait(client, "rgw/import", {"token": "match-me"}).data

    assert result["metadata"] == {"token": "********", "realm": "lab"}
    assert "ret_value" not in result


def test_wait_can_return_original_details_with_explicit_opt_in(client):
    client.request.return_value = task_list(
        finished=[
            {
                "name": "rgw/import",
                "metadata": {"token": "private"},
                "success": True,
                "ret_value": {"secret": "private"},
            }
        ]
    )

    result = task.wait(
        client,
        "rgw/import",
        {"token": "private"},
        include_secrets=True,
    ).data

    assert result["metadata"]["token"] == "private"
    assert result["ret_value"] == {"secret": "private"}


def test_wait_times_out_without_sleeping_past_deadline(client, monkeypatch):
    client.request.return_value = task_list()
    monotonic = Mock(side_effect=[0.0, 0.0, 0.1])
    sleep = Mock()
    monkeypatch.setattr(task.time, "monotonic", monotonic)
    monkeypatch.setattr(task.time, "sleep", sleep)
    with pytest.raises(TaskTimeoutError):
        task.wait(client, "service/create", timeout=0.1, interval=1)
    sleep.assert_called_once_with(0.1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"name": "bad\nname"},
        {"name": "task", "metadata": []},
        {"name": "task", "timeout": 0},
        {"name": "task", "timeout": 86401},
        {"name": "task", "interval": 0},
        {"name": "task", "interval": 61},
        {"name": "task", "fail_on_error": "true"},
        {"name": "task", "include_secrets": "true"},
    ],
)
def test_wait_rejects_invalid_arguments(client, kwargs):
    with pytest.raises(ConfigurationError):
        task.wait(client, **kwargs)
    client.request.assert_not_called()


def test_wait_rejects_finished_task_without_success(client):
    client.request.return_value = task_list(finished=[{"name": "service/create", "metadata": {}}])
    with pytest.raises(ProtocolError):
        task.wait(client, "service/create")


def test_wait_response_passes_through_synchronous_result(client):
    response = APIResponse(201, {"created": True})
    assert task.wait_response(client, response) is response


def test_wait_response_uses_accepted_task_reference(client, monkeypatch):
    response = APIResponse(
        202, {"name": "service/create", "metadata": {"service_name": "rgw.site"}}
    )
    waiter = Mock(return_value=APIResponse(200, {"success": True}))
    monkeypatch.setattr(task, "wait", waiter)
    assert task.wait_response(client, response, timeout=10).data["success"] is True
    waiter.assert_called_once_with(
        client,
        "service/create",
        {"service_name": "rgw.site"},
        10,
        2.0,
        True,
        False,
    )


@pytest.mark.parametrize("value", [None, {}, APIResponse(202, None)])
def test_wait_response_rejects_invalid_reference(client, value):
    with pytest.raises((ConfigurationError, ProtocolError)):
        task.wait_response(client, value)


def test_wait_response_rejects_non_boolean_include_secrets(client):
    with pytest.raises(ConfigurationError, match="include_secrets"):
        task.wait_response(
            client,
            APIResponse(201, {"created": True}),
            include_secrets="true",
        )
