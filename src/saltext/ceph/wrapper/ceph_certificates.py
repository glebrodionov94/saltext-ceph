"""Inspect cephadm certificates from the salt-ssh controller."""

from saltext.ceph.utils.ceph import certificate_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_certificates"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args)


def list_(
    status=None,
    scope=None,
    service_type=None,
    include_cephadm_signed=False,
    profile="default",
):
    """List certificate metadata through the controller profile."""
    return _invoke(
        certificate_api.list_,
        status,
        scope,
        service_type,
        include_cephadm_signed,
        profile,
    )


def get(service_name, profile="default"):
    """Return certificate details for an orchestrator service."""
    return _invoke(certificate_api.get, service_name, profile)


def root_ca(profile="default"):
    """Return the public cephadm root CA certificate."""
    return _invoke(certificate_api.root_ca, profile)
