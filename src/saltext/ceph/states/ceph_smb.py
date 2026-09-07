"""Declaratively reconcile current-Ceph SMB clusters and shares."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import smb
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_smb"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_smb.list_clusters",
        "ceph_smb.create_cluster",
        "ceph_smb.delete_cluster",
        "ceph_smb.list_shares",
        "ceph_smb.get_share",
        "ceph_smb.create_share",
        "ceph_smb.update_share_qos",
        "ceph_smb.delete_share",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _items(function, label, **kwargs):
    values = reconcile.data(function(**kwargs), label, expected=list)
    if not all(isinstance(item, Mapping) for item in values):
        raise ProtocolError(f"{label} returned an unexpected response shape.")
    return [dict(item) for item in values]


def _find(values, identity, value):
    return next((item for item in values if item.get(identity) == value), None)


def _desired(resource, identity, name, normalizer):
    if not isinstance(resource, Mapping):
        raise ConfigurationError("resource must be a mapping.")
    resource = dict(resource)
    if identity in resource and resource[identity] != name:
        raise ConfigurationError(f"resource {identity} does not match the state name.")
    resource[identity] = name
    return normalizer(resource)


def cluster_present(name, resource, profile="default"):
    """Ensure one current-Ceph SMB cluster resource is present and current."""
    ret = reconcile.state_result(name)
    try:
        desired = _desired(resource, "cluster_id", name, smb.normalize_cluster_resource)
        current = _find(
            _items(__salt__["ceph_smb.list_clusters"], "Ceph SMB cluster list", profile=profile),
            "cluster_id",
            name,
        )
        old = None if current is None else reconcile.project(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"Ceph SMB cluster {name} is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"Ceph SMB cluster {name} would be reconciled."
            )
        response = __salt__["ceph_smb.create_cluster"](desired, profile=profile)
        reconcile.envelope(response, "Ceph SMB cluster mutation")
        after_resource = _find(
            _items(__salt__["ceph_smb.list_clusters"], "Ceph SMB cluster list", profile=profile),
            "cluster_id",
            name,
        )
        after = None if after_resource is None else reconcile.project(after_resource, desired)
        if after != desired:
            raise ProtocolError(f"Ceph SMB cluster {name} did not converge after mutation.")
        return reconcile.changed(ret, old, after, f"Ceph SMB cluster {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def cluster_absent(name, confirm=False, profile="default"):
    """Ensure an SMB cluster is absent; removal requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = smb.validate_identifier(name, "cluster_id")
        current = _find(
            _items(__salt__["ceph_smb.list_clusters"], "Ceph SMB cluster list", profile=profile),
            "cluster_id",
            name,
        )
        if current is None:
            return reconcile.no_change(ret, f"Ceph SMB cluster {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"Ceph SMB cluster {name} would be deleted."
            )
        if confirm is not True:
            raise ConfigurationError("Deleting an SMB cluster requires confirm=True.")
        response = __salt__["ceph_smb.delete_cluster"](name, confirm=True, profile=profile)
        reconcile.envelope(response, "Ceph SMB cluster deletion")
        remaining = _find(
            _items(__salt__["ceph_smb.list_clusters"], "Ceph SMB cluster list", profile=profile),
            "cluster_id",
            name,
        )
        if remaining is not None:
            raise ProtocolError(f"Ceph SMB cluster {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"Ceph SMB cluster {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def share_present(name, cluster_id, resource, profile="default"):
    """Ensure one SMB share resource is present and current."""
    ret = reconcile.state_result(name)
    try:
        cluster_id = smb.validate_identifier(cluster_id, "cluster_id")
        desired = _desired(resource, "share_id", name, smb.normalize_share_resource)
        if desired.get("cluster_id") != cluster_id:
            raise ConfigurationError("resource cluster_id does not match cluster_id.")
        current = _find(
            _items(
                __salt__["ceph_smb.list_shares"],
                "Ceph SMB share list",
                cluster_id=cluster_id,
                profile=profile,
            ),
            "share_id",
            name,
        )
        old = None if current is None else reconcile.project(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"Ceph SMB share {cluster_id}/{name} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"Ceph SMB share {cluster_id}/{name} would be reconciled."
            )
        response = __salt__["ceph_smb.create_share"](desired, profile=profile)
        reconcile.envelope(response, "Ceph SMB share mutation")
        after_resource = _find(
            _items(
                __salt__["ceph_smb.list_shares"],
                "Ceph SMB share list",
                cluster_id=cluster_id,
                profile=profile,
            ),
            "share_id",
            name,
        )
        after = None if after_resource is None else reconcile.project(after_resource, desired)
        if after != desired:
            raise ProtocolError(f"Ceph SMB share {cluster_id}/{name} did not converge.")
        return reconcile.changed(
            ret, old, after, f"Ceph SMB share {cluster_id}/{name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def share_absent(name, cluster_id, confirm=False, profile="default"):
    """Ensure one SMB share is absent; removal requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = smb.validate_identifier(name, "share_id")
        cluster_id = smb.validate_identifier(cluster_id, "cluster_id")
        values = _items(
            __salt__["ceph_smb.list_shares"],
            "Ceph SMB share list",
            cluster_id=cluster_id,
            profile=profile,
        )
        current = _find(values, "share_id", name)
        if current is None:
            return reconcile.no_change(ret, f"Ceph SMB share {cluster_id}/{name} is absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"Ceph SMB share {cluster_id}/{name} would be deleted."
            )
        if confirm is not True:
            raise ConfigurationError("Deleting an SMB share requires confirm=True.")
        response = __salt__["ceph_smb.delete_share"](
            cluster_id, name, confirm=True, profile=profile
        )
        reconcile.envelope(response, "Ceph SMB share deletion")
        remaining = _find(
            _items(
                __salt__["ceph_smb.list_shares"],
                "Ceph SMB share list",
                cluster_id=cluster_id,
                profile=profile,
            ),
            "share_id",
            name,
        )
        if remaining is not None:
            raise ProtocolError(f"Ceph SMB share {cluster_id}/{name} still exists.")
        return reconcile.changed(
            ret, current, None, f"Ceph SMB share {cluster_id}/{name} was deleted."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def share_qos(
    name,
    cluster_id,
    read_iops_limit=None,
    write_iops_limit=None,
    read_bw_limit=None,
    write_bw_limit=None,
    read_delay_max=None,
    write_delay_max=None,
    profile="default",
):
    """Ensure the declared QoS limits on one SMB share; zero disables a limit."""
    ret = reconcile.state_result(name)
    try:
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
        limits = smb.normalize_qos_limits(limits)
        cluster_id = smb.validate_identifier(cluster_id, "cluster_id")
        name = smb.validate_identifier(name, "share_id")
        current = reconcile.data(
            __salt__["ceph_smb.get_share"](cluster_id, name, profile=profile),
            "Ceph SMB share",
            expected=Mapping,
        )
        qos = current.get("cephfs", {}).get("qos", {})
        if not isinstance(qos, Mapping):
            raise ProtocolError("Ceph SMB share returned an invalid QoS mapping.")
        old = {key: qos.get(key, 0) for key in limits}
        if old == limits:
            return reconcile.no_change(ret, f"Ceph SMB share {cluster_id}/{name} QoS is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, limits, f"Ceph SMB share {cluster_id}/{name} QoS would be updated."
            )
        response = __salt__["ceph_smb.update_share_qos"](
            cluster_id, name, profile=profile, **limits
        )
        reconcile.envelope(response, "Ceph SMB share QoS mutation")
        after_resource = reconcile.data(
            __salt__["ceph_smb.get_share"](cluster_id, name, profile=profile),
            "Ceph SMB share",
            expected=Mapping,
        )
        after_qos = after_resource.get("cephfs", {}).get("qos", {})
        after = {key: after_qos.get(key, 0) for key in limits}
        if after != limits:
            raise ProtocolError(f"Ceph SMB share {cluster_id}/{name} QoS did not converge.")
        return reconcile.changed(
            ret, old, after, f"Ceph SMB share {cluster_id}/{name} QoS was updated."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
