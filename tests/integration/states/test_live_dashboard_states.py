"""Opt-in live reconciliation tests for Ceph Dashboard states.

Every resource name and ownership marker contains a UUID generated for the
current test run.  Cleanup addresses only that exact name and verifies its
marker before deletion, never scanning or deleting by prefix.  Disposable
role/user deletion remains inside the mutation gate; the destructive gate is
reserved for existing cluster infrastructure such as hosts, OSDs, and pools.
"""

import secrets
import uuid

import pytest

from saltext.ceph.modules import ceph_dashboard_user as dashboard_user_execution
from saltext.ceph.modules import ceph_role as role_execution
from saltext.ceph.modules import ceph_task as task_execution
from saltext.ceph.states import ceph_dashboard_user as dashboard_user_state
from saltext.ceph.states import ceph_role as role_state
from saltext.ceph.utils.ceph import dashboard_user as dashboard_user_resource
from saltext.ceph.utils.ceph import dashboard_user_api
from saltext.ceph.utils.ceph import role as role_resource
from saltext.ceph.utils.ceph import role_api
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph import task as task_resource
from saltext.ceph.utils.ceph import task_api

pytestmark = pytest.mark.ceph_live

_PROFILE = "live"


@pytest.fixture
def dashboard_password_source(tmp_path):
    """Yield a restrictive temporary secret and erase it after any outcome."""
    source = tmp_path / "dashboard-user-password"
    secret_file.write(source, f"SaltextCi-{secrets.token_hex(16)}!aA9\n")
    try:
        yield source
    finally:
        source.unlink(missing_ok=True)


def _assert_no_password_material(value, source):
    """Fail without letting pytest render a leaked live password or its path."""
    rendered = repr(value)
    password = secret_file.read(source).rstrip("\r\n")
    if "password" in rendered.casefold() or password in rendered or str(source) in rendered:
        pytest.fail("A live state return exposed password material.", pytrace=False)


def _resource_identity(kind):
    """Return an exact resource name and independent ownership marker."""
    run_id = str(uuid.uuid4())
    return f"saltext-ci-{kind}-{run_id}", f"saltext-ci-owner:{run_id}"


def _configure_execution_module(monkeypatch, module):
    """Provide the loader globals normally injected by Salt."""
    monkeypatch.setattr(module, "__opts__", {}, raising=False)
    monkeypatch.setattr(module, "__pillar__", {}, raising=False)
    monkeypatch.setattr(module, "__context__", {}, raising=False)


def _bind_task_waiter(monkeypatch, live_client):
    _configure_execution_module(monkeypatch, task_execution)
    monkeypatch.setattr(task_api, "_client", lambda _opts, _pillar, _context, _profile: live_client)
    return task_execution.wait


def _bind_role_state(monkeypatch, live_client, *, test):
    """Wire the role state to its real execution-module surface."""
    _configure_execution_module(monkeypatch, role_execution)
    monkeypatch.setattr(role_api, "_client", lambda _opts, _pillar, _context, _profile: live_client)
    opts = {"test": test}
    monkeypatch.setattr(role_state, "__opts__", opts, raising=False)
    salt_functions = {
        "ceph_role.list": role_execution.list_,
        "ceph_role.create": role_execution.create,
        "ceph_role.update": role_execution.update,
        "ceph_role.delete": role_execution.delete,
        "ceph_task.wait": _bind_task_waiter(monkeypatch, live_client),
    }
    monkeypatch.setattr(role_state, "__salt__", salt_functions, raising=False)
    return opts, salt_functions


def _bind_dashboard_user_state(monkeypatch, live_client, *, test):
    """Wire the Dashboard-user state to its real execution-module surface."""
    _configure_execution_module(monkeypatch, dashboard_user_execution)
    monkeypatch.setattr(
        dashboard_user_api,
        "_client",
        lambda _opts, _pillar, _context, _profile: live_client,
    )
    opts = {"test": test}
    monkeypatch.setattr(dashboard_user_state, "__opts__", opts, raising=False)
    monkeypatch.setattr(
        dashboard_user_state,
        "__salt__",
        {
            "ceph_dashboard_user.list": dashboard_user_execution.list_,
            "ceph_dashboard_user.create": dashboard_user_execution.create,
            "ceph_dashboard_user.update": dashboard_user_execution.update,
            "ceph_dashboard_user.delete": dashboard_user_execution.delete,
            "ceph_task.wait": _bind_task_waiter(monkeypatch, live_client),
        },
        raising=False,
    )
    return opts


def _assert_write_identity(live_settings, live_client):
    """Make the exact-cluster write boundary visible in every CRUD test."""
    expected_fsid = live_settings.require_mutation()
    assert live_settings.mutate is True
    assert live_settings.connection.expected_fsid == expected_fsid
    assert live_client.config.expected_fsid == expected_fsid


def _role_exists(live_client, name):
    response = role_resource.list_(live_client)
    return any(item.get("name") == name for item in response.data)


def _user_exists(live_client, username):
    response = dashboard_user_resource.list_(live_client)
    return any(item.get("username") == username for item in response.data)


def _cleanup_role(live_client, name, ownership_marker):
    """Delete an exact role only while its ownership metadata still matches."""
    response = role_resource.list_(live_client)
    current = next((item for item in response.data if item.get("name") == name), None)
    if current is None:
        return
    if current.get("description") not in (ownership_marker, f"{ownership_marker}:updated"):
        pytest.fail("refusing to delete a role not owned by this test run")
    response = role_resource.delete(live_client, name, confirm=True)
    task_resource.wait_response(live_client, response, timeout=120.0, interval=0.5)
    assert not _role_exists(live_client, name)


def _cleanup_user(live_client, username, ownership_marker):
    """Delete an exact user only while its ownership metadata still matches."""
    response = dashboard_user_resource.list_(live_client)
    current = next((item for item in response.data if item.get("username") == username), None)
    if current is None:
        return
    if current.get("name") not in (ownership_marker, f"{ownership_marker}:updated"):
        pytest.fail("refusing to delete a Dashboard user not owned by this test run")
    response = dashboard_user_resource.delete(live_client, username, confirm=True)
    task_resource.wait_response(live_client, response, timeout=120.0, interval=0.5)
    assert not _user_exists(live_client, username)


def _unexpected_mutation(*_args, **_kwargs):
    pytest.fail("a test=True state attempted a live mutation")


def test_live_role_present_test_mode_returns_create_plan(monkeypatch, live_client):
    """A read-only run returns an exact create plan and sends no write."""
    name, ownership_marker = _resource_identity("role-plan")
    _, salt_functions = _bind_role_state(monkeypatch, live_client, test=True)
    salt_functions["ceph_role.create"] = _unexpected_mutation
    salt_functions["ceph_role.update"] = _unexpected_mutation
    salt_functions["ceph_role.delete"] = _unexpected_mutation

    result = role_state.present(
        name,
        description=ownership_marker,
        scopes_permissions={"pool": ["read"]},
        profile=_PROFILE,
    )

    assert result["result"] is None
    assert result["changes"]["old"] is None
    assert result["changes"]["new"] == {
        "name": name,
        "description": ownership_marker,
        "scopes_permissions": {"pool": ["read"]},
    }
    assert not _role_exists(live_client, name)


@pytest.mark.ceph_live_mutate
def test_live_role_state_crud_lifecycle(monkeypatch, live_settings, live_client):
    """Create, read, plan/update, plan/delete, and delete one custom role."""
    _assert_write_identity(live_settings, live_client)
    name, ownership_marker = _resource_identity("role")
    opts, _ = _bind_role_state(monkeypatch, live_client, test=False)

    # A UUID-backed name must be absent before this run claims it.  If that
    # invariant ever fails, do not delete the pre-existing role in cleanup.
    assert not _role_exists(live_client, name)
    with live_client.owned_metadata("role", name, ownership_marker):
        try:
            created = role_state.present(
                name,
                description=ownership_marker,
                scopes_permissions={"pool": ["read"]},
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert created["result"] is True
            assert created["changes"]["old"] is None
            assert created["changes"]["new"]["name"] == name

            current = role_state.present(
                name,
                description=ownership_marker,
                scopes_permissions={"pool": ["read"]},
                profile=_PROFILE,
            )
            assert current["result"] is True
            assert not current["changes"]

            opts["test"] = True
            update_plan = role_state.present(
                name,
                description=f"{ownership_marker}:updated",
                scopes_permissions={"pool": ["read", "create"]},
                profile=_PROFILE,
            )
            assert update_plan["result"] is None
            assert update_plan["changes"]["old"]["description"] == ownership_marker
            assert update_plan["changes"]["new"]["description"].endswith("updated")

            opts["test"] = False
            updated = role_state.present(
                name,
                description=f"{ownership_marker}:updated",
                scopes_permissions={"pool": ["read", "create"]},
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert updated["result"] is True
            assert updated["changes"]["new"]["scopes_permissions"] == {"pool": ["create", "read"]}

            opts["test"] = True
            delete_plan = role_state.absent(name, profile=_PROFILE)
            assert delete_plan["result"] is None
            assert delete_plan["changes"]["new"] is None
            assert _role_exists(live_client, name)

            opts["test"] = False
            refused = role_state.absent(name, profile=_PROFILE)
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert _role_exists(live_client, name)

            deleted = role_state.absent(
                name,
                confirm=True,
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert deleted["result"] is True
            assert deleted["changes"]["new"] is None
            assert not _role_exists(live_client, name)
        finally:
            _cleanup_role(live_client, name, ownership_marker)


@pytest.mark.ceph_live_mutate
def test_live_dashboard_user_state_crud_lifecycle(
    monkeypatch,
    dashboard_password_source,
    live_settings,
    live_client,
):
    """Exercise Dashboard-user plans and CRUD without exposing its password."""
    _assert_write_identity(live_settings, live_client)
    username, ownership_marker = _resource_identity("user")
    email = f"{username}@example.invalid"
    password_source = dashboard_password_source
    opts = _bind_dashboard_user_state(monkeypatch, live_client, test=True)

    assert not _user_exists(live_client, username)
    with live_client.owned_metadata("user", username, ownership_marker):
        try:
            plan = dashboard_user_state.present(
                username,
                password_source=str(password_source),
                display_name=ownership_marker,
                email=email,
                roles=["read-only"],
                pwd_update_required=False,
                profile=_PROFILE,
            )
            assert plan["result"] is None
            assert plan["changes"]["old"] is None
            _assert_no_password_material(plan, password_source)
            assert not _user_exists(live_client, username)

            opts["test"] = False
            created = dashboard_user_state.present(
                username,
                password_source=str(password_source),
                display_name=ownership_marker,
                email=email,
                roles=["read-only"],
                pwd_update_required=False,
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert created["result"] is True
            assert created["changes"]["old"] is None
            _assert_no_password_material(created, password_source)
            password_source.unlink()

            current = dashboard_user_state.present(
                username,
                display_name=ownership_marker,
                email=email,
                roles=["read-only"],
                pwd_update_required=False,
                profile=_PROFILE,
            )
            assert current["result"] is True
            assert not current["changes"]

            opts["test"] = True
            update_plan = dashboard_user_state.present(
                username,
                display_name=f"{ownership_marker}:updated",
                email=email,
                roles=["read-only"],
                pwd_update_required=False,
                profile=_PROFILE,
            )
            assert update_plan["result"] is None
            assert update_plan["changes"]["new"]["name"] == f"{ownership_marker}:updated"

            opts["test"] = False
            updated = dashboard_user_state.present(
                username,
                display_name=f"{ownership_marker}:updated",
                email=email,
                roles=["read-only"],
                pwd_update_required=False,
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert updated["result"] is True
            assert updated["changes"]["new"]["name"] == f"{ownership_marker}:updated"

            opts["test"] = True
            delete_plan = dashboard_user_state.absent(username, profile=_PROFILE)
            assert delete_plan["result"] is None
            assert delete_plan["changes"]["new"] is None
            assert _user_exists(live_client, username)

            opts["test"] = False
            refused = dashboard_user_state.absent(username, profile=_PROFILE)
            assert refused["result"] is False
            assert "confirm=True" in refused["comment"]
            assert _user_exists(live_client, username)

            deleted = dashboard_user_state.absent(
                username,
                confirm=True,
                profile=_PROFILE,
                task_interval=0.5,
            )
            assert deleted["result"] is True
            assert deleted["changes"]["new"] is None
            assert not _user_exists(live_client, username)
        finally:
            _cleanup_user(live_client, username, ownership_marker)
