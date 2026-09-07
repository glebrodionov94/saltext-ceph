"""Manage Ceph Dashboard settings through the Dashboard REST API."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import settings_api

__virtualname__ = "ceph_settings"
__func_alias__ = {"list_": "list", "set_": "set"}


def __virtual__():
    return __virtualname__


def list_(names=None, profile="default"):
    """List settings, optionally filtered by names, with secrets redacted.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_settings.list \\
          names='["PWD_POLICY_ENABLED","REST_REQUESTS_TIMEOUT"]'
    """
    return salt_adapter.invoke(
        settings_api.list_, __opts__, __pillar__, __context__, names, profile
    )


def get(name, profile="default"):
    """Return one Dashboard setting with secret values redacted.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_settings.get PWD_POLICY_ENABLED
    """
    return salt_adapter.invoke(settings_api.get, __opts__, __pillar__, __context__, name, profile)


def set_(name, value=None, source=None, profile="default"):
    """Set one Dashboard option, sourcing secrets from an absolute local file.

    CLI Examples:

    .. code-block:: bash

        salt-call --local ceph_settings.set REST_REQUESTS_TIMEOUT value=60
        salt-call --local ceph_settings.set GRAFANA_API_PASSWORD \\
          source=/run/secrets/grafana-password
    """
    return salt_adapter.invoke(
        settings_api.set_,
        __opts__,
        __pillar__,
        __context__,
        name,
        value,
        source,
        profile,
    )


def delete(name, profile="default"):
    """Reset one Dashboard setting to its default value.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_settings.delete REST_REQUESTS_TIMEOUT
    """
    return salt_adapter.invoke(
        settings_api.delete, __opts__, __pillar__, __context__, name, profile
    )


def bulk_set(values=None, secret_sources=None, profile="default"):
    """Set several Dashboard options, with secrets read from local files.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_settings.bulk_set \\
          values='{"REST_REQUESTS_TIMEOUT":60}' \\
          secret_sources='{"GRAFANA_API_PASSWORD":"/run/secrets/grafana-password"}'
    """
    return salt_adapter.invoke(
        settings_api.bulk_set,
        __opts__,
        __pillar__,
        __context__,
        values,
        secret_sources,
        profile,
    )
