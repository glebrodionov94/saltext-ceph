"""Operate the Ceph Dashboard integration with Grafana."""

from saltext.ceph.utils.ceph import grafana_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_grafana"


def __virtual__():
    return __virtualname__


def url(profile="default"):
    """Return the Grafana frontend URL exposed by Ceph Dashboard.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_grafana.url
    """
    return salt_adapter.invoke(grafana_api.url, __opts__, __pillar__, __context__, profile)


def validate_dashboard(dashboard_uid, profile="default"):
    """Return Grafana's HTTP status for one dashboard UID.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_grafana.validate_dashboard ceph-cluster
    """
    return salt_adapter.invoke(
        grafana_api.validate_dashboard,
        __opts__,
        __pillar__,
        __context__,
        dashboard_uid,
        profile,
    )


def push_dashboards(profile="default"):
    """Push Ceph's bundled dashboards to the configured Grafana instance.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_grafana.push_dashboards
    """
    return salt_adapter.invoke(
        grafana_api.push_dashboards, __opts__, __pillar__, __context__, profile
    )
