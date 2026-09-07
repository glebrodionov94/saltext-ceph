"""Salt-facing composition for current-only multi-cluster operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import multi_cluster
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import ConfigurationError


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def _secret(source, label, *, optional=False):
    if source is None and optional:
        return None
    value = secret_file.read(source).rstrip("\r\n")
    if not value:
        raise ConfigurationError(f"{label} file contains only line separators.")
    return value


def connect(
    opts,
    pillar,
    context,
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
    """Connect a remote Ceph cluster to the local multi-cluster hub."""
    return multi_cluster.connect(
        _client(opts, pillar, context, profile),
        url,
        cluster_alias,
        username,
        _secret(password_source, "Password"),
        hub_url,
        ssl_verify,
        _secret(ssl_certificate_source, "TLS certificate", optional=True),
        ttl,
        allow_http,
    ).as_dict()


def set_current(opts, pillar, context, url, username, allow_http=False, profile="default"):
    """Select the current cluster for multi-cluster Dashboard operations."""
    return multi_cluster.set_current(
        _client(opts, pillar, context, profile), url, username, allow_http
    ).as_dict()


def reconnect(
    opts,
    pillar,
    context,
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
    """Refresh credentials and reconnect an existing remote cluster."""
    return multi_cluster.reconnect(
        _client(opts, pillar, context, profile),
        url,
        username,
        _secret(password_source, "Password", optional=True),
        _secret(cluster_token_source, "Cluster token", optional=True),
        ssl_verify,
        _secret(ssl_certificate_source, "TLS certificate", optional=True),
        ttl,
        allow_http,
    ).as_dict()


def edit(
    opts,
    pillar,
    context,
    cluster_name,
    url,
    cluster_alias,
    username,
    ssl_verify=None,
    ssl_certificate_source=None,
    allow_http=False,
    profile="default",
):
    """Update the connection metadata for a managed cluster."""
    return multi_cluster.edit(
        _client(opts, pillar, context, profile),
        cluster_name,
        url,
        cluster_alias,
        username,
        ssl_verify,
        _secret(ssl_certificate_source, "TLS certificate", optional=True),
        allow_http,
    ).as_dict()


def delete(
    opts,
    pillar,
    context,
    cluster_name,
    cluster_user,
    confirm=False,
    profile="default",
):
    """Remove a cluster connection after explicit confirmation."""
    return multi_cluster.delete(
        _client(opts, pillar, context, profile), cluster_name, cluster_user, confirm
    ).as_dict()


def get_config(opts, pillar, context, include_secrets=False, profile="default"):
    """Return the Dashboard multi-cluster configuration."""
    return multi_cluster.get_config(
        _client(opts, pillar, context, profile), include_secrets
    ).as_dict()


def token_status(opts, pillar, context, profile="default"):
    """Return the authentication token status for connected clusters."""
    return multi_cluster.token_status(_client(opts, pillar, context, profile)).as_dict()


def security_config(opts, pillar, context, profile="default"):
    """Return the multi-cluster security configuration."""
    return multi_cluster.security_config(_client(opts, pillar, context, profile)).as_dict()


def prometheus_api_url(opts, pillar, context, profile="default"):
    """Return the Prometheus API URL configured for multi-cluster use."""
    return multi_cluster.prometheus_api_url(_client(opts, pillar, context, profile)).as_dict()
