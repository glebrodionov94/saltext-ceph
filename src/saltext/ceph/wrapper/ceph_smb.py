"""Manage current Ceph SMB resources from salt-ssh."""

from saltext.ceph.utils.ceph import salt as salt_adapter
from saltext.ceph.utils.ceph import smb_api

__virtualname__ = "ceph_smb"


def __virtual__():
    return __virtualname__


def _invoke(function, *args, **kwargs):
    return salt_adapter.invoke(function, __opts__, {}, __context__, *args, **kwargs)


def list_clusters(profile="default"):
    """List SMB clusters."""
    return _invoke(smb_api.list_clusters, profile)


def get_cluster(cluster_id, profile="default"):
    """Return one SMB cluster."""
    return _invoke(smb_api.get_cluster, cluster_id, profile)


def create_cluster(resource, profile="default"):
    """Create or replace an SMB cluster resource."""
    return _invoke(smb_api.create_cluster, resource, profile)


def delete_cluster(cluster_id, confirm=False, profile="default"):
    """Delete an SMB cluster after explicit confirmation."""
    return _invoke(smb_api.delete_cluster, cluster_id, confirm, profile)


def list_shares(cluster_id=None, profile="default"):
    """List all SMB shares, optionally for one cluster."""
    return _invoke(smb_api.list_shares, cluster_id, profile)


def get_share(cluster_id, share_id, profile="default"):
    """Return one SMB share."""
    return _invoke(smb_api.get_share, cluster_id, share_id, profile)


def create_share(resource, profile="default"):
    """Create or replace an SMB share resource."""
    return _invoke(smb_api.create_share, resource, profile)


def update_share_qos(
    cluster_id,
    share_id,
    read_iops_limit=None,
    write_iops_limit=None,
    read_bw_limit=None,
    write_bw_limit=None,
    read_delay_max=None,
    write_delay_max=None,
    profile="default",
):
    """Update the explicitly supplied QoS limits on an SMB share."""
    return _invoke(
        smb_api.update_share_qos,
        cluster_id,
        share_id,
        read_iops_limit,
        write_iops_limit,
        read_bw_limit,
        write_bw_limit,
        read_delay_max,
        write_delay_max,
        profile,
    )


def delete_share(cluster_id, share_id, confirm=False, profile="default"):
    """Delete an SMB share after explicit confirmation."""
    return _invoke(smb_api.delete_share, cluster_id, share_id, confirm, profile)


def list_join_auths(profile="default"):
    """List SMB domain join credentials with passwords redacted."""
    return _invoke(smb_api.list_join_auths, profile)


def get_join_auth(auth_id, profile="default"):
    """Return one SMB domain join resource with its password redacted."""
    return _invoke(smb_api.get_join_auth, auth_id, profile)


def create_join_auth(
    auth_id,
    username,
    password_source,
    linked_to_cluster=None,
    profile="default",
):
    """Create domain join credentials using a local password file."""
    return _invoke(
        smb_api.create_join_auth,
        auth_id,
        username,
        password_source,
        linked_to_cluster,
        profile,
    )


def delete_join_auth(auth_id, confirm=False, profile="default"):
    """Delete domain join credentials after explicit confirmation."""
    return _invoke(smb_api.delete_join_auth, auth_id, confirm, profile)


def list_usersgroups(profile="default"):
    """List SMB users/groups resources with passwords redacted."""
    return _invoke(smb_api.list_usersgroups, profile)


def get_usersgroups(users_groups_id, profile="default"):
    """Return one users/groups resource with passwords redacted."""
    return _invoke(smb_api.get_usersgroups, users_groups_id, profile)


def create_usersgroups(
    users_groups_id,
    source,
    linked_to_cluster=None,
    profile="default",
):
    """Create users/groups from a protected local JSON file."""
    return _invoke(
        smb_api.create_usersgroups,
        users_groups_id,
        source,
        linked_to_cluster,
        profile,
    )


def delete_usersgroups(users_groups_id, confirm=False, profile="default"):
    """Delete an SMB users/groups resource after confirmation."""
    return _invoke(smb_api.delete_usersgroups, users_groups_id, confirm, profile)
