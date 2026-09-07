"""Salt-facing composition for Dashboard certificate inspection."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import certificates


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(
    opts,
    pillar,
    context,
    status=None,
    scope=None,
    service_type=None,
    include_cephadm_signed=False,
    profile="default",
):
    """List certificate metadata."""
    return certificates.list_(
        _client(opts, pillar, context, profile),
        status,
        scope,
        service_type,
        include_cephadm_signed,
    ).as_dict()


def get(opts, pillar, context, service_name, profile="default"):
    """Return certificate details for an orchestrator service."""
    return certificates.get(_client(opts, pillar, context, profile), service_name).as_dict()


def root_ca(opts, pillar, context, profile="default"):
    """Return the public cephadm root CA certificate."""
    return certificates.root_ca(_client(opts, pillar, context, profile)).as_dict()
