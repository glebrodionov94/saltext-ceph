"""Salt-facing composition for Prometheus controller operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import prometheus


def _call(function, opts, pillar, context, profile, *args):
    client = ceph.get_client(opts, pillar, context, profile)
    return function(client, *args).as_dict()


def alerts(opts, pillar, context, params=None, cluster_filter=False, profile="default"):
    """Return active Prometheus alerts."""
    return _call(prometheus.alerts, opts, pillar, context, profile, params, cluster_filter)


def rules(opts, pillar, context, params=None, profile="default"):
    """Return Prometheus alerting and recording rules."""
    return _call(prometheus.rules, opts, pillar, context, profile, params)


def query_range(
    opts,
    pillar,
    context,
    expression,
    start=None,
    end=None,
    step=None,
    params=None,
    profile="default",
):
    """Run a Prometheus range query."""
    return _call(
        prometheus.query_range,
        opts,
        pillar,
        context,
        profile,
        expression,
        start,
        end,
        step,
        params,
    )


def query(opts, pillar, context, expression, params=None, profile="default"):
    """Run an instant Prometheus query."""
    return _call(prometheus.query, opts, pillar, context, profile, expression, params)


def silences(opts, pillar, context, params=None, profile="default"):
    """Return Alertmanager silences."""
    return _call(prometheus.silences, opts, pillar, context, profile, params)


def create_silence(opts, pillar, context, silence, profile="default"):
    """Create an Alertmanager silence."""
    return _call(prometheus.create_silence, opts, pillar, context, profile, silence)


def delete_silence(opts, pillar, context, silence_id, confirm=False, profile="default"):
    """Delete an Alertmanager silence after explicit confirmation."""
    return _call(
        prometheus.delete_silence,
        opts,
        pillar,
        context,
        profile,
        silence_id,
        confirm,
    )


def alert_groups(opts, pillar, context, params=None, cluster_filter=False, profile="default"):
    """Return grouped Prometheus alerts."""
    return _call(
        prometheus.alert_groups,
        opts,
        pillar,
        context,
        profile,
        params,
        cluster_filter,
    )


def notifications(opts, pillar, context, from_=None, profile="default"):
    """Return Prometheus notifications from an optional cursor."""
    return _call(prometheus.notifications, opts, pillar, context, profile, from_)


def set_remote_write(opts, pillar, context, url, allowed_metrics, profile="default"):
    """Configure the Prometheus remote-write destination and metric allowlist."""
    return _call(
        prometheus.set_remote_write,
        opts,
        pillar,
        context,
        profile,
        url,
        allowed_metrics,
    )


def remove_remote_write(opts, pillar, context, url, confirm=False, profile="default"):
    """Remove a Prometheus remote-write destination after confirmation."""
    return _call(
        prometheus.remove_remote_write,
        opts,
        pillar,
        context,
        profile,
        url,
        confirm,
    )
