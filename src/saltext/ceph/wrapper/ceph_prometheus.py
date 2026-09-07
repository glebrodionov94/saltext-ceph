"""Query and operate Ceph's Prometheus integration from salt-ssh."""

from saltext.ceph.utils.ceph import prometheus_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_prometheus"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def alerts(params=None, cluster_filter=False, profile="default"):
    """Return Alertmanager alerts proxied by Dashboard."""
    return _invoke(prometheus_api.alerts, params, cluster_filter, profile)


def rules(params=None, profile="default"):
    """Return Prometheus recording and alerting rules."""
    return _invoke(prometheus_api.rules, params, profile)


def query_range(
    expression,
    start=None,
    end=None,
    step=None,
    params=None,
    profile="default",
):
    """Run a Prometheus range query through Dashboard."""
    return _invoke(
        prometheus_api.query_range,
        expression,
        start,
        end,
        step,
        params,
        profile,
    )


def query(expression, params=None, profile="default"):
    """Run an instant Prometheus query on current Ceph."""
    return _invoke(prometheus_api.query, expression, params, profile)


def silences(params=None, profile="default"):
    """Return Alertmanager silences."""
    return _invoke(prometheus_api.silences, params, profile)


def create_silence(silence, profile="default"):
    """Create an Alertmanager silence from a JSON mapping."""
    return _invoke(prometheus_api.create_silence, silence, profile)


def delete_silence(silence_id, confirm=False, profile="default"):
    """Delete one Alertmanager silence; requires ``confirm=True``."""
    return _invoke(prometheus_api.delete_silence, silence_id, confirm, profile)


def alert_groups(params=None, cluster_filter=False, profile="default"):
    """Return Alertmanager alert groups on current Ceph."""
    return _invoke(prometheus_api.alert_groups, params, cluster_filter, profile)


def notifications(from_=None, profile="default"):
    """Return alert notifications received by this Dashboard process."""
    return _invoke(prometheus_api.notifications, from_, profile)


def set_remote_write(url, allowed_metrics, profile="default"):
    """Set a remote-write target on current Ceph."""
    return _invoke(prometheus_api.set_remote_write, url, allowed_metrics, profile)


def remove_remote_write(url, confirm=False, profile="default"):
    """Remove a remote-write target; requires ``confirm=True``."""
    return _invoke(prometheus_api.remove_remote_write, url, confirm, profile)
