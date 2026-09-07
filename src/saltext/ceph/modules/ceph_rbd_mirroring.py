"""Manage RBD mirroring through the public Ceph Dashboard REST API."""

from saltext.ceph.utils.ceph import rbd_mirroring_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_rbd_mirroring"


def __virtual__():
    return __virtualname__


def _call(operation, *args, profile="default", **kwargs):
    return salt_adapter.invoke(
        rbd_mirroring_api.call,
        __opts__,
        __pillar__,
        __context__,
        operation,
        *args,
        profile=profile,
        **kwargs,
    )


def summary(profile="default"):
    """Return the summary. CLI Example: ``salt-call --local ceph_rbd_mirroring.summary``"""
    return _call("summary", profile=profile)


def image_summary(pool_name, image_name, profile="default"):
    """Return image status. CLI Example: ``salt-call --local ceph_rbd_mirroring.image_summary rbd vm-1``"""
    return _call("image_summary", pool_name, image_name, profile=profile)


def get_site_name(profile="default"):
    """Return the site. CLI Example: ``salt-call --local ceph_rbd_mirroring.get_site_name``"""
    return _call("get_site_name", profile=profile)


def set_site_name(site_name, profile="default"):
    """Set the site. CLI Example: ``salt-call --local ceph_rbd_mirroring.set_site_name site-a``"""
    return _call("set_site_name", site_name, profile=profile)


def get_pool_mode(pool_name, profile="default"):
    """Return pool mode. CLI Example: ``salt-call --local ceph_rbd_mirroring.get_pool_mode rbd``"""
    return _call("get_pool_mode", pool_name, profile=profile)


def set_pool_mode(pool_name, mirror_mode, confirm=False, profile="default"):
    """Set pool mode. CLI Example: ``salt-call --local ceph_rbd_mirroring.set_pool_mode rbd image``"""
    return _call("set_pool_mode", pool_name, mirror_mode, confirm, profile=profile)


def create_bootstrap_token(pool_name, destination, overwrite=False, profile="default"):
    """Save a token. CLI Example: ``salt-call --local ceph_rbd_mirroring.create_bootstrap_token rbd /tmp/token``"""
    return salt_adapter.invoke(
        rbd_mirroring_api.create_bootstrap_token,
        __opts__,
        __pillar__,
        __context__,
        pool_name,
        destination,
        overwrite,
        profile,
    )


def import_bootstrap_token(pool_name, source, direction="rx-tx", profile="default"):
    """Import a token. CLI Example: ``salt-call --local ceph_rbd_mirroring.import_bootstrap_token rbd /tmp/token``"""
    return salt_adapter.invoke(
        rbd_mirroring_api.import_bootstrap_token,
        __opts__,
        __pillar__,
        __context__,
        pool_name,
        source,
        direction,
        profile,
    )


def list_peers(pool_name, profile="default"):
    """List peers. CLI Example: ``salt-call --local ceph_rbd_mirroring.list_peers rbd``"""
    return _call("list_peers", pool_name, profile=profile)


def get_peer(pool_name, peer_uuid, profile="default"):
    """Return a peer. CLI Example: ``salt-call --local ceph_rbd_mirroring.get_peer rbd UUID``"""
    return _call("get_peer", pool_name, peer_uuid, profile=profile)


def create_peer(
    pool_name,
    cluster_name,
    client_id,
    mon_host=None,
    key_source=None,
    profile="default",
):
    """Create a peer. CLI Example: ``salt-call --local ceph_rbd_mirroring.create_peer rbd remote mirror``"""
    return salt_adapter.invoke(
        rbd_mirroring_api.create_peer,
        __opts__,
        __pillar__,
        __context__,
        pool_name,
        cluster_name,
        client_id,
        mon_host,
        key_source,
        profile,
    )


def update_peer(
    pool_name,
    peer_uuid,
    cluster_name=None,
    client_id=None,
    mon_host=None,
    key_source=None,
    clear_key=False,
    profile="default",
):
    """Update a peer. CLI Example: ``salt-call --local ceph_rbd_mirroring.update_peer rbd UUID cluster_name=remote``"""
    return salt_adapter.invoke(
        rbd_mirroring_api.update_peer,
        __opts__,
        __pillar__,
        __context__,
        pool_name,
        peer_uuid,
        cluster_name,
        client_id,
        mon_host,
        key_source,
        clear_key,
        profile,
    )


def delete_peer(pool_name, peer_uuid, confirm=False, profile="default"):
    """Delete a peer. CLI Example: ``salt-call --local ceph_rbd_mirroring.delete_peer rbd UUID confirm=true``"""
    return _call("delete_peer", pool_name, peer_uuid, confirm, profile=profile)
