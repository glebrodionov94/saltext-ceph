"""Shared authentication operations retain profile and cache semantics."""

from unittest.mock import Mock

import pytest

from saltext.ceph.utils.ceph import auth
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.client import CephClient
from saltext.ceph.utils.ceph.errors import APIError


@pytest.fixture
def loader_data():
    opts = {
        "ceph": {
            "profiles": {
                "default": {"url": "https://ceph.example", "username": "salt", "password": "secret"}
            }
        }
    }
    return opts, {}, {}


def test_login_and_check_are_serializable(loader_data, monkeypatch):
    opts, pillar, context = loader_data
    reply = APIResponse(201, {"username": "salt"})
    login = Mock(return_value=reply)
    check = Mock(return_value=reply)
    monkeypatch.setattr(CephClient, "login", login)
    monkeypatch.setattr(CephClient, "check", check)

    assert auth.login(opts, pillar, context, ttl=3) == {
        "status": 201,
        "data": {"username": "salt"},
        "headers": {},
    }
    assert auth.check(opts, pillar, context)["data"] == {"username": "salt"}
    login.assert_called_once_with(ttl=3)
    check.assert_called_once_with()


def test_logout_always_removes_cached_client(loader_data, monkeypatch):
    opts, pillar, context = loader_data
    logout = Mock(side_effect=APIError(401))
    monkeypatch.setattr(CephClient, "logout", logout)
    with pytest.raises(APIError):
        auth.logout(opts, pillar, context)
    assert context["saltext.ceph.clients"] == {}
