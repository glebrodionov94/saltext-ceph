"""Salt-facing composition for Grafana controller operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import grafana


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def url(opts, pillar, context, profile="default"):
    """Return the configured Grafana frontend URL."""
    return grafana.url(_client(opts, pillar, context, profile)).as_dict()


def validate_dashboard(opts, pillar, context, dashboard_uid, profile="default"):
    """Return Grafana's HTTP status for one dashboard UID."""
    return grafana.validate_dashboard(
        _client(opts, pillar, context, profile), dashboard_uid
    ).as_dict()


def push_dashboards(opts, pillar, context, profile="default"):
    """Push Ceph's local dashboards to the configured Grafana instance."""
    return grafana.push_dashboards(_client(opts, pillar, context, profile)).as_dict()
