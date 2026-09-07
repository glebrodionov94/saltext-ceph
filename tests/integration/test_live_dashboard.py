"""Opt-in, read-only smoke tests against a real Ceph Dashboard."""

import uuid

import pytest

from saltext.ceph.utils.ceph import health

pytestmark = pytest.mark.ceph_live


def test_live_health_is_a_mapping(live_client):
    """Verify authentication, TLS, API versioning, and JSON decoding."""
    response = health.minimal(live_client)
    assert response.status == 200
    assert isinstance(response.data, dict)


def test_live_cluster_fsid_is_valid_and_expected(live_client, live_settings):
    """Verify cluster identity without performing a mutation."""
    response = health.fsid(live_client)
    actual = str(uuid.UUID(response.data))
    expected = live_settings.connection.expected_fsid
    if expected:
        assert actual == str(uuid.UUID(expected))
