"""Salt-facing composition for OSD controller operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import osd


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def _call(function, opts, pillar, context, profile, *args):
    return function(_client(opts, pillar, context, profile), *args).as_dict()


def list_(
    opts,
    pillar,
    context,
    offset=0,
    limit=-1,
    search="",
    sort="+id",
    profile="default",
):
    """Return OSDs."""
    return _call(osd.list_, opts, pillar, context, profile, offset, limit, search, sort)


def get(opts, pillar, context, svc_id, profile="default"):
    """Return one OSD."""
    return _call(osd.get, opts, pillar, context, profile, svc_id)


def settings(opts, pillar, context, profile="default"):
    """Return OSD fullness settings."""
    return _call(osd.settings, opts, pillar, context, profile)


def smart(opts, pillar, context, svc_id, profile="default"):
    """Return OSD SMART data."""
    return _call(osd.smart, opts, pillar, context, profile, svc_id)


def histogram(opts, pillar, context, svc_id, profile="default"):
    """Return an OSD histogram."""
    return _call(osd.histogram, opts, pillar, context, profile, svc_id)


def devices(opts, pillar, context, svc_id, profile="default"):
    """Return OSD devices."""
    return _call(osd.devices, opts, pillar, context, profile, svc_id)


def set_device_class(opts, pillar, context, svc_id, device_class, profile="default"):
    """Set or clear an OSD device class."""
    return _call(osd.set_device_class, opts, pillar, context, profile, svc_id, device_class)


def create(
    opts,
    pillar,
    context,
    method,
    data,
    tracking_id,
    confirm=False,
    profile="default",
):
    """Create OSDs."""
    return _call(
        osd.create,
        opts,
        pillar,
        context,
        profile,
        method,
        data,
        tracking_id,
        confirm,
    )


def remove(
    opts,
    pillar,
    context,
    svc_id,
    preserve_id=False,
    force=False,
    confirm=False,
    profile="default",
):
    """Remove an OSD."""
    return _call(
        osd.remove,
        opts,
        pillar,
        context,
        profile,
        svc_id,
        preserve_id,
        force,
        confirm,
    )


def scrub(opts, pillar, context, svc_id, deep=False, profile="default"):
    """Scrub an OSD."""
    return _call(osd.scrub, opts, pillar, context, profile, svc_id, deep)


def mark(opts, pillar, context, svc_id, action, confirm=False, profile="default"):
    """Mark an OSD."""
    return _call(osd.mark, opts, pillar, context, profile, svc_id, action, confirm)


def reweight(opts, pillar, context, svc_id, weight, profile="default"):
    """Temporarily reweight an OSD."""
    return _call(osd.reweight, opts, pillar, context, profile, svc_id, weight)


def purge(opts, pillar, context, svc_id, confirm=False, profile="default"):
    """Purge an OSD."""
    return _call(osd.purge, opts, pillar, context, profile, svc_id, confirm)


def destroy(opts, pillar, context, svc_id, confirm=False, profile="default"):
    """Destroy an OSD while retaining its ID."""
    return _call(osd.destroy, opts, pillar, context, profile, svc_id, confirm)


def safe_to_destroy(opts, pillar, context, ids, profile="default"):
    """Check whether OSDs are safe to destroy."""
    return _call(osd.safe_to_destroy, opts, pillar, context, profile, ids)


def safe_to_delete(opts, pillar, context, svc_ids, profile="default"):
    """Check whether OSD health permits removal."""
    return _call(osd.safe_to_delete, opts, pillar, context, profile, svc_ids)


def flags(opts, pillar, context, profile="default"):
    """Return cluster-wide OSD flags."""
    return _call(osd.flags, opts, pillar, context, profile)


def set_flags(
    opts, pillar, context, flags, profile="default"
):  # pylint: disable=redefined-outer-name
    """Replace cluster-wide OSD flags."""
    return _call(osd.set_flags, opts, pillar, context, profile, flags)


def individual_flags(opts, pillar, context, profile="default"):
    """Return per-OSD flags."""
    return _call(osd.individual_flags, opts, pillar, context, profile)


def set_individual_flags(  # pylint: disable=redefined-outer-name
    opts, pillar, context, flags, ids, profile="default"
):
    """Set or clear per-OSD flags."""
    return _call(osd.set_individual_flags, opts, pillar, context, profile, flags, ids)
