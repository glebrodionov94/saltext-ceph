"""Declaratively manage current-Ceph RBD groups and group snapshots."""

from collections.abc import Mapping
from collections.abc import Sequence

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_rbd_group"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)


def __virtual__():
    required = {
        "ceph_rbd_group.list",
        "ceph_rbd_group.get",
        "ceph_rbd_group.create",
        "ceph_rbd_group.delete",
        "ceph_rbd_group.add_image",
        "ceph_rbd_group.remove_image",
        "ceph_rbd_group.snapshot_list",
        "ceph_rbd_group.snapshot_create",
        "ceph_rbd_group.snapshot_delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _scope(pool_name, namespace):
    return (
        validation.identifier(pool_name, "pool_name"),
        None if namespace is None else validation.identifier(namespace, "namespace"),
    )


def _desired_images(images):
    if images is None:
        return None
    if isinstance(images, (str, bytes)) or not isinstance(images, Sequence):
        raise ConfigurationError("images must be a list or null.")
    result = [validation.identifier(value, "image_name") for value in images]
    if len(set(result)) != len(result):
        raise ConfigurationError("images must not contain duplicates.")
    return sorted(result)


def _listed_group(pool_name, namespace, group_name, profile):
    items = reconcile.data(
        __salt__["ceph_rbd_group.list"](pool_name, namespace=namespace, profile=profile),
        "Ceph RBD group list",
        expected=list,
    )
    matches = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("group"), str):
            raise ProtocolError("Ceph RBD group list returned an unexpected response shape.")
        count = item.get("num_images")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ProtocolError("Ceph RBD group list returned an unexpected response shape.")
        item_name = item["group"]
        if item_name in seen:
            raise ProtocolError("Ceph RBD group list returned duplicate groups.")
        seen.add(item_name)
        if item_name == group_name:
            matches.append(count)
    return matches[0] if matches else None


def _member_names(pool_name, namespace, group_name, profile):
    data = reconcile.data(
        __salt__["ceph_rbd_group.get"](pool_name, group_name, namespace=namespace, profile=profile),
        "Ceph RBD group read",
        expected=list,
    )
    if len(data) != 1 or not isinstance(data[0], Mapping):
        raise ProtocolError("Ceph RBD group read returned an unexpected response shape.")
    images = data[0].get("images")
    if not isinstance(images, list):
        raise ProtocolError("Ceph RBD group read returned invalid image membership.")
    names = []
    for image in images:
        if not isinstance(image, Mapping) or not isinstance(image.get("name"), str):
            raise ProtocolError("Ceph RBD group read returned invalid image membership.")
        names.append(image["name"])
    if len(set(names)) != len(names):
        raise ProtocolError("Ceph RBD group read returned duplicate image membership.")
    return sorted(names)


def _current(pool_name, namespace, group_name, images, profile):
    count = _listed_group(pool_name, namespace, group_name, profile)
    if count is None:
        return None
    result = {
        "pool_name": pool_name,
        "namespace": namespace,
        "group": group_name,
    }
    if images is not None:
        members = _member_names(pool_name, namespace, group_name, profile)
        if count != len(members):
            raise ProtocolError("Ceph RBD group list and detail disagree on image count.")
        result["images"] = members
    return result


def _wait(response, profile, task_timeout, task_interval):
    reconcile.wait_if_accepted(
        __salt__,
        response,
        profile=profile,
        timeout=task_timeout,
        interval=task_interval,
    )


def present(
    name,
    pool_name,
    namespace=None,
    images=None,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a group exists and optionally manage its complete member set.

    Passing ``images=None`` manages only group existence. An explicit list,
    including an empty list, is the complete desired membership. Removing a
    member changes the consistency set and therefore requires ``confirm=True``.
    """
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "group_name")
        pool_name, namespace = _scope(pool_name, namespace)
        images = _desired_images(images)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        desired = {
            "pool_name": pool_name,
            "namespace": namespace,
            "group": name,
        }
        if images is not None:
            desired["images"] = images
        current = _current(pool_name, namespace, name, images, profile)
        if current == desired:
            return reconcile.no_change(ret, f"RBD group {pool_name}/{name} is already current.")

        current_images = [] if current is None else current.get("images", [])
        extra = sorted(set(current_images).difference(images or [])) if images is not None else []
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"RBD group {pool_name}/{name} would be reconciled."
            )
        if extra and not confirm:
            raise ConfigurationError("Removing RBD group members requires confirm=True.")

        if current is None:
            response = __salt__["ceph_rbd_group.create"](
                pool_name, name, namespace=namespace, profile=profile
            )
            _wait(response, profile, task_timeout, task_interval)
            if _current(pool_name, namespace, name, None, profile) is None:
                raise ProtocolError(f"RBD group {pool_name}/{name} did not appear after creation.")

        if images is not None:
            members = [] if current is None else _member_names(pool_name, namespace, name, profile)
            missing = sorted(set(images).difference(members))
            extra = sorted(set(members).difference(images))
            for image_name in missing:
                response = __salt__["ceph_rbd_group.add_image"](
                    pool_name,
                    name,
                    image_name,
                    namespace=namespace,
                    profile=profile,
                )
                _wait(response, profile, task_timeout, task_interval)
            for image_name in extra:
                response = __salt__["ceph_rbd_group.remove_image"](
                    pool_name,
                    name,
                    image_name,
                    namespace=namespace,
                    confirm=True,
                    profile=profile,
                )
                _wait(response, profile, task_timeout, task_interval)

        after = _current(pool_name, namespace, name, images, profile)
        if after != desired:
            raise ProtocolError(f"RBD group {pool_name}/{name} did not converge.")
        return reconcile.changed(
            ret, current, after, f"RBD group {pool_name}/{name} was reconciled."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def absent(
    name,
    pool_name,
    namespace=None,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a group is absent after removing its membership."""
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "group_name")
        pool_name, namespace = _scope(pool_name, namespace)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        current = _current(pool_name, namespace, name, [], profile)
        if current is None:
            return reconcile.no_change(ret, f"RBD group {pool_name}/{name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"RBD group {pool_name}/{name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting an RBD group requires confirm=True.")
        for image_name in current["images"]:
            response = __salt__["ceph_rbd_group.remove_image"](
                pool_name,
                name,
                image_name,
                namespace=namespace,
                confirm=True,
                profile=profile,
            )
            _wait(response, profile, task_timeout, task_interval)
        response = __salt__["ceph_rbd_group.delete"](
            pool_name, name, namespace=namespace, confirm=True, profile=profile
        )
        _wait(response, profile, task_timeout, task_interval)
        if _current(pool_name, namespace, name, None, profile) is not None:
            raise ProtocolError(f"RBD group {pool_name}/{name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RBD group {pool_name}/{name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _snapshot(pool_name, namespace, group_name, snapshot_name, profile):
    items = reconcile.data(
        __salt__["ceph_rbd_group.snapshot_list"](
            pool_name, group_name, namespace=namespace, profile=profile
        ),
        "Ceph RBD group snapshot list",
        expected=list,
    )
    matches = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ProtocolError(
                "Ceph RBD group snapshot list returned an unexpected response shape."
            )
        item_name = item["name"]
        if item_name in seen:
            raise ProtocolError("Ceph RBD group snapshot list returned duplicate snapshots.")
        seen.add(item_name)
        if item_name == snapshot_name:
            matches.append(
                {
                    "pool_name": pool_name,
                    "namespace": namespace,
                    "group": group_name,
                    "snapshot": snapshot_name,
                }
            )
    return matches[0] if matches else None


def snapshot_present(
    name,
    pool_name,
    group_name,
    namespace=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a crash-consistent RBD group snapshot exists."""
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "snapshot_name")
        group_name = validation.identifier(group_name, "group_name")
        pool_name, namespace = _scope(pool_name, namespace)
        desired = {
            "pool_name": pool_name,
            "namespace": namespace,
            "group": group_name,
            "snapshot": name,
        }
        if _current(pool_name, namespace, group_name, None, profile) is None:
            raise ConfigurationError(f"Parent RBD group {pool_name}/{group_name} does not exist.")
        current = _snapshot(pool_name, namespace, group_name, name, profile)
        if current == desired:
            return reconcile.no_change(
                ret, f"RBD group snapshot {pool_name}/{group_name}@{name} already exists."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                desired,
                f"RBD group snapshot {pool_name}/{group_name}@{name} would be created.",
            )
        response = __salt__["ceph_rbd_group.snapshot_create"](
            pool_name,
            group_name,
            name,
            namespace=namespace,
            flags=0,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        after = _snapshot(pool_name, namespace, group_name, name, profile)
        if after != desired:
            raise ProtocolError(
                f"RBD group snapshot {pool_name}/{group_name}@{name} did not appear."
            )
        return reconcile.changed(
            ret,
            current,
            after,
            f"RBD group snapshot {pool_name}/{group_name}@{name} was created.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def snapshot_absent(
    name,
    pool_name,
    group_name,
    namespace=None,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure an RBD group snapshot is absent; deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "snapshot_name")
        group_name = validation.identifier(group_name, "group_name")
        pool_name, namespace = _scope(pool_name, namespace)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        if _current(pool_name, namespace, group_name, None, profile) is None:
            return reconcile.no_change(
                ret, f"RBD group snapshot {pool_name}/{group_name}@{name} is already absent."
            )
        current = _snapshot(pool_name, namespace, group_name, name, profile)
        if current is None:
            return reconcile.no_change(
                ret, f"RBD group snapshot {pool_name}/{group_name}@{name} is already absent."
            )
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                None,
                f"RBD group snapshot {pool_name}/{group_name}@{name} would be deleted.",
            )
        if not confirm:
            raise ConfigurationError("Deleting an RBD group snapshot requires confirm=True.")
        response = __salt__["ceph_rbd_group.snapshot_delete"](
            pool_name,
            group_name,
            name,
            namespace=namespace,
            confirm=True,
            profile=profile,
        )
        _wait(response, profile, task_timeout, task_interval)
        if _snapshot(pool_name, namespace, group_name, name, profile) is not None:
            raise ProtocolError(
                f"RBD group snapshot {pool_name}/{group_name}@{name} still exists after deletion."
            )
        return reconcile.changed(
            ret,
            current,
            None,
            f"RBD group snapshot {pool_name}/{group_name}@{name} was deleted.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
