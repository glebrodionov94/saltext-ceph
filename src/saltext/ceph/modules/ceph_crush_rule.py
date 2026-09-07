"""Manage CRUSH rules through the Ceph Dashboard REST API."""

from saltext.ceph.utils.ceph import crush_rule_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_crush_rule"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(profile="default"):
    """Return all CRUSH rules.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_crush_rule.list
    """
    return salt_adapter.invoke(crush_rule_api.list_, __opts__, __pillar__, __context__, profile)


def get(name, profile="default"):
    """Return one CRUSH rule by name.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_crush_rule.get replicated_ssd
    """
    return salt_adapter.invoke(crush_rule_api.get, __opts__, __pillar__, __context__, name, profile)


def create(
    name,
    failure_domain,
    device_class=None,
    root=None,
    erasure_profile=None,
    pool_type="replication",
    profile="default",
):
    """Create a replicated rule or a current-Ceph erasure rule.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_crush_rule.create replicated_ssd host \\
          root=default device_class=ssd
    """
    return salt_adapter.invoke(
        crush_rule_api.create,
        __opts__,
        __pillar__,
        __context__,
        name,
        failure_domain,
        device_class,
        root,
        erasure_profile,
        pool_type,
        profile,
    )


def delete(name, confirm=False, profile="default"):
    """Delete one CRUSH rule after explicit confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_crush_rule.delete replicated_ssd confirm=true
    """
    return salt_adapter.invoke(
        crush_rule_api.delete, __opts__, __pillar__, __context__, name, confirm, profile
    )
