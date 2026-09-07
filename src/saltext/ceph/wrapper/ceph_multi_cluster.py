"""Manage Dashboard multi-cluster connections from a salt-ssh controller."""

from saltext.ceph.utils.ceph import multi_cluster_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_multi_cluster"


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def connect(
    url,
    cluster_alias,
    username,
    password_source,
    hub_url,
    ssl_verify=None,
    ssl_certificate_source=None,
    ttl=None,
    allow_http=False,
    profile="default",
):
    """Register a remote cluster using controller-local files."""
    return _invoke(
        multi_cluster_api.connect,
        url,
        cluster_alias,
        username,
        password_source,
        hub_url,
        ssl_verify,
        ssl_certificate_source,
        ttl,
        allow_http,
        profile,
    )


def set_current(url, username, allow_http=False, profile="default"):
    """Select an already configured cluster and user."""
    return _invoke(multi_cluster_api.set_current, url, username, allow_http, profile)


def reconnect(
    url,
    username,
    password_source=None,
    cluster_token_source=None,
    ssl_verify=None,
    ssl_certificate_source=None,
    ttl=None,
    allow_http=False,
    profile="default",
):
    """Refresh a connection from one controller-local credential file."""
    return _invoke(
        multi_cluster_api.reconnect,
        url,
        username,
        password_source,
        cluster_token_source,
        ssl_verify,
        ssl_certificate_source,
        ttl,
        allow_http,
        profile,
    )


def edit(
    cluster_name,
    url,
    cluster_alias,
    username,
    ssl_verify=None,
    ssl_certificate_source=None,
    allow_http=False,
    profile="default",
):
    """Edit the public properties of a configured remote cluster."""
    return _invoke(
        multi_cluster_api.edit,
        cluster_name,
        url,
        cluster_alias,
        username,
        ssl_verify,
        ssl_certificate_source,
        allow_http,
        profile,
    )


def delete(cluster_name, cluster_user, confirm=False, profile="default"):
    """Remove a remote connection after explicit confirmation."""
    return _invoke(multi_cluster_api.delete, cluster_name, cluster_user, confirm, profile)


def get_config(include_secrets=False, profile="default"):
    """Return configuration with stored tokens redacted by default."""
    return _invoke(multi_cluster_api.get_config, include_secrets, profile)


def token_status(profile="default"):
    """Return expiry status for remote-cluster tokens."""
    return _invoke(multi_cluster_api.token_status, profile)


def security_config(profile="default"):
    """Return cephadm management-gateway security status."""
    return _invoke(multi_cluster_api.security_config, profile)


def prometheus_api_url(profile="default"):
    """Return this cluster's advertised Prometheus API URL."""
    return _invoke(multi_cluster_api.prometheus_api_url, profile)
