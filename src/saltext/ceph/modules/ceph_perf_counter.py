"""Inspect Ceph daemon performance counters through Dashboard."""

from saltext.ceph.utils.ceph import perf_counter_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_perf_counter"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(profile="default"):
    """Return all unlabeled performance counters.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_perf_counter.list
    """
    return salt_adapter.invoke(perf_counter_api.list_, __opts__, __pillar__, __context__, profile)


def get(service_type, service_id, profile="default"):
    """Return counters for one mds, mgr, mon, osd, rgw, mirror or iSCSI daemon.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_perf_counter.get osd 0
    """
    return salt_adapter.invoke(
        perf_counter_api.get,
        __opts__,
        __pillar__,
        __context__,
        service_type,
        service_id,
        profile,
    )
