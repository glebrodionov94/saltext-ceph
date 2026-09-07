"""Manage cephadm services through the Ceph Dashboard REST API."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import service_api

__virtualname__ = "ceph_service"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, *args)


def list_(
    service_name=None,
    offset=0,
    limit=-1,
    search="",
    sort="+service_name",
    profile="default",
):
    """List cephadm services, returning every matching service by default.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_service.list service_name=rgw.realm.zone
    """
    return _invoke(
        service_api.list_,
        service_name,
        offset,
        limit,
        search,
        sort,
        profile,
    )


def get(service_name, profile="default"):
    """Return one cephadm service.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_service.get rgw.realm.zone
    """
    return _invoke(service_api.get, service_name, profile)


def known_types(profile="default"):
    """Return the service types known to the connected Ceph release.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_service.known_types
    """
    return _invoke(service_api.known_types, profile)


def daemons(service_name, profile="default"):
    """Return daemons belonging to one cephadm service.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_service.daemons rgw.realm.zone
    """
    return _invoke(service_api.daemons, service_name, profile)


def create(service_name, service_spec, profile="default"):
    """Create a cephadm service from a structured ServiceSpec mapping.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_service.create rgw.realm.zone \\
          service_spec='{"service_type":"rgw","service_id":"realm.zone",\\
          "placement":{"label":"rgw"}}'
    """
    return _invoke(service_api.create, service_name, service_spec, profile)


def update(service_name, service_spec, profile="default"):
    """Replace the declarative ServiceSpec of a cephadm service.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_service.update rgw.realm.zone \\
          service_spec='{"service_type":"rgw","service_id":"realm.zone",\\
          "placement":{"count":3,"label":"rgw"}}'
    """
    return _invoke(service_api.update, service_name, service_spec, profile)


def delete(service_name, confirm=False, profile="default"):
    """Remove a cephadm service and its daemons after confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_service.delete rgw.realm.zone confirm=true
    """
    return _invoke(service_api.delete, service_name, confirm, profile)
