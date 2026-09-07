"""Salt-facing composition for current Ceph SMB operations."""

import json
from collections.abc import Mapping

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph import smb
from saltext.ceph.utils.ceph.errors import ConfigurationError


def _call(function, opts, pillar, context, profile, *args, **kwargs):
    client = ceph.get_client(opts, pillar, context, profile)
    return function(client, *args, **kwargs).as_dict()


def _secret(source, label):
    value = secret_file.read(source).rstrip("\r\n")
    if not value:
        raise ConfigurationError(f"{label} file contains no usable value.")
    return value


def list_clusters(opts, pillar, context, profile="default"):
    """List SMB clusters."""
    return _call(smb.list_clusters, opts, pillar, context, profile)


def get_cluster(opts, pillar, context, cluster_id, profile="default"):
    """Return one SMB cluster."""
    return _call(smb.get_cluster, opts, pillar, context, profile, cluster_id)


def create_cluster(opts, pillar, context, resource, profile="default"):
    """Create an SMB cluster from a cluster resource."""
    return _call(smb.create_cluster, opts, pillar, context, profile, resource)


def delete_cluster(opts, pillar, context, cluster_id, confirm=False, profile="default"):
    """Delete an SMB cluster after explicit confirmation."""
    return _call(smb.delete_cluster, opts, pillar, context, profile, cluster_id, confirm)


def list_shares(opts, pillar, context, cluster_id=None, profile="default"):
    """List SMB shares, optionally for one cluster."""
    return _call(smb.list_shares, opts, pillar, context, profile, cluster_id)


def get_share(opts, pillar, context, cluster_id, share_id, profile="default"):
    """Return one SMB share."""
    return _call(smb.get_share, opts, pillar, context, profile, cluster_id, share_id)


def create_share(opts, pillar, context, resource, profile="default"):
    """Create an SMB share from a share resource."""
    return _call(smb.create_share, opts, pillar, context, profile, resource)


def update_share_qos(
    opts,
    pillar,
    context,
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
    """Update explicitly supplied QoS limits for an SMB share."""
    limits = {
        key: value
        for key, value in {
            "read_iops_limit": read_iops_limit,
            "write_iops_limit": write_iops_limit,
            "read_bw_limit": read_bw_limit,
            "write_bw_limit": write_bw_limit,
            "read_delay_max": read_delay_max,
            "write_delay_max": write_delay_max,
        }.items()
        if value is not None
    }
    return _call(
        smb.update_share_qos,
        opts,
        pillar,
        context,
        profile,
        cluster_id,
        share_id,
        **limits,
    )


def delete_share(
    opts,
    pillar,
    context,
    cluster_id,
    share_id,
    confirm=False,
    profile="default",
):
    """Delete an SMB share after explicit confirmation."""
    return _call(
        smb.delete_share,
        opts,
        pillar,
        context,
        profile,
        cluster_id,
        share_id,
        confirm,
    )


def list_join_auths(opts, pillar, context, profile="default"):
    """List SMB join-auth resources."""
    return _call(smb.list_join_auths, opts, pillar, context, profile)


def get_join_auth(opts, pillar, context, auth_id, profile="default"):
    """Return one SMB join-auth resource."""
    return _call(smb.get_join_auth, opts, pillar, context, profile, auth_id)


def create_join_auth(
    opts,
    pillar,
    context,
    auth_id,
    username,
    password_source,
    linked_to_cluster=None,
    profile="default",
):
    """Create an SMB join-auth resource using a password file."""
    return _call(
        smb.create_join_auth,
        opts,
        pillar,
        context,
        profile,
        auth_id,
        username,
        _secret(password_source, "password"),
        linked_to_cluster,
    )


def delete_join_auth(opts, pillar, context, auth_id, confirm=False, profile="default"):
    """Delete an SMB join-auth resource after explicit confirmation."""
    return _call(smb.delete_join_auth, opts, pillar, context, profile, auth_id, confirm)


def list_usersgroups(opts, pillar, context, profile="default"):
    """List SMB users/groups resources."""
    return _call(smb.list_usersgroups, opts, pillar, context, profile)


def get_usersgroups(opts, pillar, context, users_groups_id, profile="default"):
    """Return one SMB users/groups resource."""
    return _call(smb.get_usersgroups, opts, pillar, context, profile, users_groups_id)


def create_usersgroups(
    opts,
    pillar,
    context,
    users_groups_id,
    source,
    linked_to_cluster=None,
    profile="default",
):
    """Create an SMB users/groups resource from a JSON file."""
    try:
        values = json.loads(secret_file.read(source))
    except json.JSONDecodeError:
        raise ConfigurationError("SMB users/groups source must contain JSON.") from None
    if not isinstance(values, Mapping):
        raise ConfigurationError("SMB users/groups source must contain a JSON object.")
    return _call(
        smb.create_usersgroups,
        opts,
        pillar,
        context,
        profile,
        users_groups_id,
        values,
        linked_to_cluster,
    )


def delete_usersgroups(
    opts,
    pillar,
    context,
    users_groups_id,
    confirm=False,
    profile="default",
):
    """Delete an SMB users/groups resource after explicit confirmation."""
    return _call(
        smb.delete_usersgroups,
        opts,
        pillar,
        context,
        profile,
        users_groups_id,
        confirm,
    )
