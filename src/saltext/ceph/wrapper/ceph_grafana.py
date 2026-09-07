"""Operate the Ceph Dashboard Grafana integration from salt-ssh."""

from saltext.ceph.utils.ceph import grafana_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_grafana"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def url(profile="default"):
    """Return the Grafana frontend URL exposed by Ceph Dashboard."""
    return _invoke(grafana_api.url, profile)


def validate_dashboard(dashboard_uid, profile="default"):
    """Return Grafana's HTTP status for one dashboard UID."""
    return _invoke(grafana_api.validate_dashboard, dashboard_uid, profile)


def push_dashboards(profile="default"):
    """Push Ceph's bundled dashboards to the configured Grafana instance."""
    return _invoke(grafana_api.push_dashboards, profile)
