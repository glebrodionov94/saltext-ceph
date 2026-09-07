"""Declaratively reconcile NFS-Ganesha exports."""

from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import nfs
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_nfs"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_nfs.list_exports",
        "ceph_nfs.create_export",
        "ceph_nfs.update_export",
        "ceph_nfs.delete_export",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _find(cluster_id, pseudo, profile):
    values = reconcile.data(
        __salt__["ceph_nfs.list_exports"](profile=profile),
        "Ceph NFS export list",
        expected=list,
    )
    matches = [
        dict(item)
        for item in values
        if isinstance(item, Mapping)
        and item.get("cluster_id") == cluster_id
        and item.get("pseudo") == pseudo
    ]
    if len(matches) > 1:
        raise ProtocolError("Ceph returned duplicate NFS exports for cluster_id and pseudo.")
    return matches[0] if matches else None


def _view(current, desired):
    if current is None:
        return None
    return reconcile.project(current, desired)


def present(
    name,
    cluster_id,
    path,
    access_type="RW",
    squash="root_squash",
    security_label=False,
    protocols=None,
    transports=None,
    fsal=None,
    clients=None,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure the NFS export identified by ``cluster_id`` and pseudo ``name`` exists."""
    ret = reconcile.state_result(name)
    try:
        protocols = [4] if protocols is None else protocols
        transports = ["TCP"] if transports is None else transports
        clients = [] if clients is None else clients
        desired = nfs.normalize_export(
            path,
            cluster_id,
            name,
            access_type,
            squash,
            security_label,
            protocols,
            transports,
            fsal,
            clients,
        )
        cluster_id = desired["cluster_id"]
        pseudo = desired["pseudo"]
        current = _find(cluster_id, pseudo, profile)
        old = _view(current, desired)
        if old == desired:
            return reconcile.no_change(ret, f"Ceph NFS export {cluster_id}:{pseudo} is current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, old, desired, f"Ceph NFS export {cluster_id}:{pseudo} would be reconciled."
            )
        kwargs = {key: value for key, value in desired.items() if key != "cluster_id"}
        if current is None:
            response = __salt__["ceph_nfs.create_export"](
                cluster_id=cluster_id, profile=profile, **kwargs
            )
        else:
            export_id = nfs.validate_export_id(current.get("export_id"))
            response = __salt__["ceph_nfs.update_export"](
                cluster_id, export_id, profile=profile, **kwargs
            )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _view(_find(cluster_id, pseudo, profile), desired)
        if after != desired:
            raise ProtocolError(f"Ceph NFS export {cluster_id}:{pseudo} did not converge.")
        return reconcile.changed(
            ret, old, after, f"Ceph NFS export {cluster_id}:{pseudo} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    cluster_id,
    confirm=False,
    profile="default",
    task_timeout=600.0,
    task_interval=2.0,
):
    """Ensure an NFS export is absent; removal requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        cluster_id = nfs.validate_cluster_id(cluster_id)
        pseudo = nfs.validate_pseudo(name)
        current = _find(cluster_id, pseudo, profile)
        if current is None:
            return reconcile.no_change(
                ret, f"Ceph NFS export {cluster_id}:{pseudo} is already absent."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"Ceph NFS export {cluster_id}:{pseudo} would be deleted."
            )
        if confirm is not True:
            raise ConfigurationError("Deleting an NFS export requires confirm=True.")
        export_id = nfs.validate_export_id(current.get("export_id"))
        response = __salt__["ceph_nfs.delete_export"](
            cluster_id, export_id, confirm=True, profile=profile
        )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        if _find(cluster_id, pseudo, profile) is not None:
            raise ProtocolError(f"Ceph NFS export {cluster_id}:{pseudo} still exists.")
        return reconcile.changed(
            ret, current, None, f"Ceph NFS export {cluster_id}:{pseudo} was deleted."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
