"""Manage Ceph OSDs through the Dashboard REST API."""

from saltext.ceph.utils.ceph import osd_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_osd"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, *args)


def list_(offset=0, limit=-1, search="", sort="+id", profile="default"):
    """Return every OSD by default.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.list
    """
    return _invoke(osd_api.list_, offset, limit, search, sort, profile)


def get(svc_id, profile="default"):
    """Return collected data for one OSD.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.get svc_id=7
    """
    return _invoke(osd_api.get, svc_id, profile)


def settings(profile="default"):
    """Return cluster near-full and full ratios.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.settings
    """
    return _invoke(osd_api.settings, profile)


def smart(svc_id, profile="default"):
    """Return SMART data for one OSD.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.smart svc_id=7
    """
    return _invoke(osd_api.smart, svc_id, profile)


def histogram(svc_id, profile="default"):
    """Return an OSD performance histogram.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.histogram svc_id=7
    """
    return _invoke(osd_api.histogram, svc_id, profile)


def devices(svc_id, profile="default"):
    """Return device-health records associated with one OSD.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.devices svc_id=7
    """
    return _invoke(osd_api.devices, svc_id, profile)


def set_device_class(svc_id, device_class, profile="default"):
    """Set a CRUSH device class, or clear it with an empty string.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.set_device_class svc_id=7 device_class=nvme
    """
    return _invoke(osd_api.set_device_class, svc_id, device_class, profile)


def create(method, data, tracking_id, confirm=False, profile="default"):
    """Create OSDs; requires ``confirm=true``.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.create method=drive_groups \\
          data='[{"service_type":"osd","placement":{"hosts":["node1"]}}]' \\
          tracking_id=osd-plan-1 confirm=true
    """
    return _invoke(osd_api.create, method, data, tracking_id, confirm, profile)


def remove(
    svc_id,
    preserve_id=False,
    force=False,
    confirm=False,
    profile="default",
):
    """Schedule OSD removal; requires ``confirm=true``.

    ``force=false`` is sent explicitly so Dashboard performs its health check.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.remove svc_id=7 confirm=true
    """
    return _invoke(osd_api.remove, svc_id, preserve_id, force, confirm, profile)


def scrub(svc_id, deep=False, profile="default"):
    """Schedule a regular or deep scrub.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.scrub svc_id=7 deep=true
    """
    return _invoke(osd_api.scrub, svc_id, deep, profile)


def mark(svc_id, action, confirm=False, profile="default"):
    """Mark an OSD in, out, down, or lost.

    The irreversible ``lost`` action requires ``confirm=true``.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.mark svc_id=7 action=out
        salt-call --local ceph_osd.mark svc_id=7 action=lost confirm=true
    """
    return _invoke(osd_api.mark, svc_id, action, confirm, profile)


def reweight(svc_id, weight, profile="default"):
    """Temporarily set an OSD weight between zero and one.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.reweight svc_id=7 weight=0.8
    """
    return _invoke(osd_api.reweight, svc_id, weight, profile)


def purge(svc_id, confirm=False, profile="default"):
    """Permanently purge a down OSD; requires ``confirm=true``.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.purge svc_id=7 confirm=true
    """
    return _invoke(osd_api.purge, svc_id, confirm, profile)


def destroy(svc_id, confirm=False, profile="default"):
    """Destroy a down OSD while retaining its ID; requires ``confirm=true``.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.destroy svc_id=7 confirm=true
    """
    return _invoke(osd_api.destroy, svc_id, confirm, profile)


def safe_to_destroy(ids, profile="default"):
    """Check whether one or more OSDs are safe to destroy.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.safe_to_destroy ids='[7,8]'
    """
    return _invoke(osd_api.safe_to_destroy, ids, profile)


def safe_to_delete(svc_ids, profile="default"):
    """Check whether cluster health permits OSD removal.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.safe_to_delete svc_ids='[7,8]'
    """
    return _invoke(osd_api.safe_to_delete, svc_ids, profile)


def flags(profile="default"):
    """Return cluster-wide OSD flags.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.flags
    """
    return _invoke(osd_api.flags, profile)


def set_flags(flags, profile="default"):  # pylint: disable=redefined-outer-name
    """Replace the complete cluster-wide OSD flag list.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.set_flags flags='["noout","sortbitwise"]'
    """
    return _invoke(osd_api.set_flags, flags, profile)


def individual_flags(profile="default"):
    """Return individual flags for every OSD.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.individual_flags
    """
    return _invoke(osd_api.individual_flags, profile)


def set_individual_flags(flags, ids, profile="default"):  # pylint: disable=redefined-outer-name
    """Set or clear supported flags for selected OSDs.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_osd.set_individual_flags \\
          flags='{"noout":true,"noup":false}' ids='[7,8]'
    """
    return _invoke(osd_api.set_individual_flags, flags, ids, profile)
