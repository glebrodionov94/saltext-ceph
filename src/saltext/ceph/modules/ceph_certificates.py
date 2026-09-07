"""Inspect certificates managed by cephadm through Dashboard REST API.

This controller is available in current Ceph and is absent in Reef. It exposes
certificate metadata and public certificate material; it does not return private
keys.
"""

from saltext.ceph.utils.ceph import certificate_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_certificates"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(
    status=None,
    scope=None,
    service_type=None,
    include_cephadm_signed=False,
    profile="default",
):
    """List certificates. CLI Example: ``salt-call --local ceph_certificates.list``"""
    return salt_adapter.invoke(
        certificate_api.list_,
        __opts__,
        __pillar__,
        __context__,
        status,
        scope,
        service_type,
        include_cephadm_signed,
        profile,
    )


def get(service_name, profile="default"):
    """Read service certificate. CLI Example: ``salt-call --local ceph_certificates.get rgw.site``"""
    return salt_adapter.invoke(
        certificate_api.get,
        __opts__,
        __pillar__,
        __context__,
        service_name,
        profile,
    )


def root_ca(profile="default"):
    """Read public root CA. CLI Example: ``salt-call --local ceph_certificates.root_ca``"""
    return salt_adapter.invoke(certificate_api.root_ca, __opts__, __pillar__, __context__, profile)
