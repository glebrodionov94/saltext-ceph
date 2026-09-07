"""Manage Ceph OSDs from salt-ssh."""

from saltext.ceph.utils.ceph import osd_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_osd"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(offset=0, limit=-1, search="", sort="+id", profile="default"):
    """Return every OSD by default."""
    return _invoke(osd_api.list_, offset, limit, search, sort, profile)


def get(svc_id, profile="default"):
    """Return collected data for one OSD."""
    return _invoke(osd_api.get, svc_id, profile)


def settings(profile="default"):
    """Return cluster near-full and full ratios."""
    return _invoke(osd_api.settings, profile)


def smart(svc_id, profile="default"):
    """Return SMART data for one OSD."""
    return _invoke(osd_api.smart, svc_id, profile)


def histogram(svc_id, profile="default"):
    """Return an OSD performance histogram."""
    return _invoke(osd_api.histogram, svc_id, profile)


def devices(svc_id, profile="default"):
    """Return device-health records associated with one OSD."""
    return _invoke(osd_api.devices, svc_id, profile)


def set_device_class(svc_id, device_class, profile="default"):
    """Set or clear an OSD CRUSH device class."""
    return _invoke(osd_api.set_device_class, svc_id, device_class, profile)


def create(method, data, tracking_id, confirm=False, profile="default"):
    """Create OSDs after an explicit confirmation."""
    return _invoke(osd_api.create, method, data, tracking_id, confirm, profile)


def remove(
    svc_id,
    preserve_id=False,
    force=False,
    confirm=False,
    profile="default",
):
    """Schedule OSD removal after an explicit confirmation."""
    return _invoke(osd_api.remove, svc_id, preserve_id, force, confirm, profile)


def scrub(svc_id, deep=False, profile="default"):
    """Schedule a regular or deep scrub."""
    return _invoke(osd_api.scrub, svc_id, deep, profile)


def mark(svc_id, action, confirm=False, profile="default"):
    """Mark an OSD in, out, down, or lost."""
    return _invoke(osd_api.mark, svc_id, action, confirm, profile)


def reweight(svc_id, weight, profile="default"):
    """Temporarily reweight an OSD."""
    return _invoke(osd_api.reweight, svc_id, weight, profile)


def purge(svc_id, confirm=False, profile="default"):
    """Permanently purge a down OSD."""
    return _invoke(osd_api.purge, svc_id, confirm, profile)


def destroy(svc_id, confirm=False, profile="default"):
    """Destroy a down OSD while retaining its ID."""
    return _invoke(osd_api.destroy, svc_id, confirm, profile)


def safe_to_destroy(ids, profile="default"):
    """Check whether OSDs are safe to destroy."""
    return _invoke(osd_api.safe_to_destroy, ids, profile)


def safe_to_delete(svc_ids, profile="default"):
    """Check whether cluster health permits OSD removal."""
    return _invoke(osd_api.safe_to_delete, svc_ids, profile)


def flags(profile="default"):
    """Return cluster-wide OSD flags."""
    return _invoke(osd_api.flags, profile)


def set_flags(flags, profile="default"):  # pylint: disable=redefined-outer-name
    """Replace cluster-wide OSD flags."""
    return _invoke(osd_api.set_flags, flags, profile)


def individual_flags(profile="default"):
    """Return individual flags for every OSD."""
    return _invoke(osd_api.individual_flags, profile)


def set_individual_flags(flags, ids, profile="default"):  # pylint: disable=redefined-outer-name
    """Set or clear supported flags for selected OSDs."""
    return _invoke(osd_api.set_individual_flags, flags, ids, profile)
