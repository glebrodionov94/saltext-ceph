"""Opt-in, read-only smoke tests against a real Ceph Dashboard."""

import os
import uuid

import pytest

from saltext.ceph.utils.ceph import health
from saltext.ceph.utils.ceph.client import CephClient
from saltext.ceph.utils.ceph.config import ConnectionConfig


def _environment():
    url = os.environ.get("CEPH_TEST_URL")
    if not url:
        pytest.skip("CEPH_TEST_URL is not configured", allow_module_level=True)
    token = os.environ.get("CEPH_TEST_TOKEN")
    username = os.environ.get("CEPH_TEST_USERNAME")
    password = os.environ.get("CEPH_TEST_PASSWORD")
    verify_value = os.environ.get("CEPH_TEST_VERIFY", "true")
    if verify_value.casefold() in ("true", "1"):
        verify = True
    elif verify_value.casefold() in ("false", "0"):
        verify = False
    else:
        verify = verify_value
    return ConnectionConfig(
        url=url,
        token=token,
        username=username,
        password=password,
        verify=verify,
        allow_http=os.environ.get("CEPH_TEST_ALLOW_HTTP") == "1",
        expected_fsid=os.environ.get("CEPH_TEST_EXPECTED_FSID"),
    )


@pytest.fixture(scope="module")
def live_client():
    """Create one explicitly configured real-cluster client."""
    client = CephClient(_environment())
    try:
        yield client
    finally:
        client.close()


def test_live_health_is_a_mapping(live_client):
    """Verify authentication, TLS, API versioning, and JSON decoding."""
    response = health.minimal(live_client)
    assert response.status == 200
    assert isinstance(response.data, dict)


def test_live_cluster_fsid_is_valid_and_expected(live_client):
    """Verify cluster identity without performing a mutation."""
    response = health.fsid(live_client)
    actual = str(uuid.UUID(response.data))
    expected = os.environ.get("CEPH_TEST_EXPECTED_FSID")
    if expected:
        assert actual == str(uuid.UUID(expected))
