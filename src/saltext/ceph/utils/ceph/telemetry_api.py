"""Salt-facing composition for Dashboard telemetry operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import telemetry


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def report(opts, pillar, context, profile="default"):
    """Return the current telemetry report preview."""
    return telemetry.report(_client(opts, pillar, context, profile)).as_dict()


def set_(opts, pillar, context, enable=True, license_name=None, profile="default"):
    """Enable or disable periodic telemetry submission."""
    return telemetry.set_(_client(opts, pillar, context, profile), enable, license_name).as_dict()
