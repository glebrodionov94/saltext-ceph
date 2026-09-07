"""Declaratively manage observable RBD mirroring configuration."""

import re
import uuid
from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import rbd_mirroring
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_rbd_mirroring"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_rbd_mirroring.get_site_name",
        "ceph_rbd_mirroring.set_site_name",
        "ceph_rbd_mirroring.get_pool_mode",
        "ceph_rbd_mirroring.set_pool_mode",
        "ceph_rbd_mirroring.list_peers",
        "ceph_rbd_mirroring.get_peer",
        "ceph_rbd_mirroring.create_peer",
        "ceph_rbd_mirroring.update_peer",
        "ceph_rbd_mirroring.delete_peer",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _text(value, label, *, allow_empty=False, max_length=4096):
    if (
        not isinstance(value, str)
        or len(value) > max_length
        or (not value and not allow_empty)
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise ConfigurationError(f"{label} must be bounded single-line text.")
    return value


def _site(profile):
    data = reconcile.data(
        __salt__["ceph_rbd_mirroring.get_site_name"](profile=profile),
        "Ceph RBD mirroring site read",
        expected=Mapping,
    )
    if not isinstance(data.get("site_name"), str):
        raise ProtocolError("Ceph RBD mirroring site returned an unexpected response shape.")
    return {"site_name": data["site_name"]}


def site_name_managed(
    name,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure the local RBD mirroring site has exactly ``name``."""
    ret = reconcile.state_result(name)
    try:
        desired = {"site_name": _text(name, "site_name", max_length=255)}
        current = _site(profile)
        if current == desired:
            return reconcile.no_change(ret, "RBD mirroring site name is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, "RBD mirroring site name would be updated."
            )
        response = __salt__["ceph_rbd_mirroring.set_site_name"](name, profile=profile)
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        after = _site(profile)
        if after != desired:
            raise ProtocolError("RBD mirroring site name did not converge.")
        return reconcile.changed(ret, current, after, "RBD mirroring site name was updated.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _pool_mode(pool_name, profile):
    data = reconcile.data(
        __salt__["ceph_rbd_mirroring.get_pool_mode"](pool_name, profile=profile),
        "Ceph RBD pool mirroring read",
        expected=Mapping,
    )
    mode = data.get("mirror_mode")
    if not isinstance(mode, str) or mode not in rbd_mirroring.POOL_MODES:
        raise ProtocolError("Ceph RBD pool mirroring returned an unknown mode.")
    return {"pool_name": pool_name, "mirror_mode": mode}


def pool_mode_managed(
    name,
    mirror_mode,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure an RBD pool has exactly the requested mirroring mode."""
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "pool_name")
        if not isinstance(mirror_mode, str) or mirror_mode not in rbd_mirroring.POOL_MODES:
            raise ConfigurationError(
                f"mirror_mode must be one of: {', '.join(sorted(rbd_mirroring.POOL_MODES))}."
            )
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        desired = {"pool_name": name, "mirror_mode": mirror_mode}
        current = _pool_mode(name, profile)
        if current == desired:
            return reconcile.no_change(ret, f"RBD pool {name} mirroring mode is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"RBD pool {name} mirroring mode would be updated."
            )
        if mirror_mode == "disabled" and not confirm:
            raise ConfigurationError("Disabling RBD pool mirroring requires confirm=True.")
        response = __salt__["ceph_rbd_mirroring.set_pool_mode"](
            name,
            mirror_mode,
            confirm=mirror_mode == "disabled",
            profile=profile,
        )
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        after = _pool_mode(name, profile)
        if after != desired:
            raise ProtocolError(f"RBD pool {name} mirroring mode did not converge.")
        return reconcile.changed(
            ret, current, after, f"RBD pool {name} mirroring mode was updated."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _canonical_uuid(value):
    if not isinstance(value, str):
        raise ProtocolError("Ceph RBD mirroring peer list returned an invalid UUID.")
    try:
        normalized = str(uuid.UUID(value))
    except ValueError:
        raise ProtocolError("Ceph RBD mirroring peer list returned an invalid UUID.") from None
    if value.lower() != normalized:
        raise ProtocolError("Ceph RBD mirroring peer list returned an invalid UUID.")
    return normalized


def _peer_view(item, peer_uuid):
    if not isinstance(item, Mapping) or item.get("uuid") != peer_uuid:
        raise ProtocolError("Ceph RBD mirroring peer returned an unexpected response shape.")
    cluster_name = item.get("cluster_name")
    site_name = item.get("site_name")
    if cluster_name is None:
        cluster_name = site_name
    elif site_name is not None and site_name != cluster_name:
        raise ProtocolError("Ceph RBD mirroring peer returned conflicting site names.")
    client_id = item.get("client_id")
    mon_host = item.get("mon_host", "")
    if not all(isinstance(value, str) for value in (cluster_name, client_id, mon_host)):
        raise ProtocolError("Ceph RBD mirroring peer returned an unexpected response shape.")
    return {
        "cluster_name": cluster_name,
        "client_id": client_id,
        "mon_host": mon_host,
    }


def _peer(pool_name, cluster_name, profile):
    identifiers = reconcile.data(
        __salt__["ceph_rbd_mirroring.list_peers"](pool_name, profile=profile),
        "Ceph RBD mirroring peer list",
        expected=list,
    )
    identifiers = [_canonical_uuid(value) for value in identifiers]
    if len(set(identifiers)) != len(identifiers):
        raise ProtocolError("Ceph RBD mirroring peer list returned duplicate UUIDs.")
    matches = []
    for peer_uuid in identifiers:
        item = reconcile.data(
            __salt__["ceph_rbd_mirroring.get_peer"](pool_name, peer_uuid, profile=profile),
            "Ceph RBD mirroring peer read",
            expected=Mapping,
        )
        public = _peer_view(item, peer_uuid)
        if public["cluster_name"] == cluster_name:
            matches.append((peer_uuid, public))
    if len(matches) > 1:
        raise ConfigurationError(
            f"Multiple RBD mirroring peers use cluster_name {cluster_name}; state identity is ambiguous."
        )
    return matches[0] if matches else (None, None)


def _validate_key_source(source):
    if source is not None:
        secret_file.read(source)


def peer_present(
    name,
    pool_name,
    client_id,
    mon_host="",
    key_source=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a uniquely named legacy peer has the declared public fields.

    ``key_source`` is create-only because Dashboard deliberately does not expose
    a key fingerprint or another value suitable for drift comparison.
    """
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "cluster_name")
        pool_name = validation.identifier(pool_name, "pool_name")
        client_id = validation.identifier(client_id, "client_id")
        mon_host = _text(mon_host, "mon_host", allow_empty=True)
        desired = {
            "cluster_name": name,
            "client_id": client_id,
            "mon_host": mon_host,
        }
        peer_uuid, current = _peer(pool_name, name, profile)
        if current == desired:
            return reconcile.no_change(ret, f"RBD mirroring peer {name} is already current.")
        if current is None and __opts__.get("test", False):
            _validate_key_source(key_source)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"RBD mirroring peer {name} would be reconciled."
            )
        if current is None:
            response = __salt__["ceph_rbd_mirroring.create_peer"](
                pool_name,
                name,
                client_id,
                mon_host=mon_host,
                key_source=key_source,
                profile=profile,
            )
        else:
            changes = {key: value for key, value in desired.items() if current.get(key) != value}
            response = __salt__["ceph_rbd_mirroring.update_peer"](
                pool_name,
                peer_uuid,
                cluster_name=changes.get("cluster_name"),
                client_id=changes.get("client_id"),
                mon_host=changes.get("mon_host"),
                key_source=None,
                clear_key=False,
                profile=profile,
            )
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        _, after = _peer(pool_name, name, profile)
        if after != desired:
            raise ProtocolError(f"RBD mirroring peer {name} did not converge.")
        return reconcile.changed(ret, current, after, f"RBD mirroring peer {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def peer_absent(
    name,
    pool_name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a uniquely named legacy mirroring peer is absent."""
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "cluster_name")
        pool_name = validation.identifier(pool_name, "pool_name")
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        peer_uuid, current = _peer(pool_name, name, profile)
        if current is None:
            return reconcile.no_change(ret, f"RBD mirroring peer {name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"RBD mirroring peer {name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting an RBD mirroring peer requires confirm=True.")
        response = __salt__["ceph_rbd_mirroring.delete_peer"](
            pool_name, peer_uuid, confirm=True, profile=profile
        )
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        _, after = _peer(pool_name, name, profile)
        if after is not None:
            raise ProtocolError(f"RBD mirroring peer {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RBD mirroring peer {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
