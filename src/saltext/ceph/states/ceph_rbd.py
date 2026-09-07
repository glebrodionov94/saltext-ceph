"""Declaratively manage RBD images, image snapshots, and namespaces."""

import math
import re
from collections.abc import Mapping

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import rbd
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import validation
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_rbd"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_SENSITIVE_WORDS = ("PASSWORD", "SECRET", "TOKEN", "KEY")
_CONFIGURATION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_MUTABLE_FEATURES_ENABLE = frozenset(("exclusive-lock", "object-map", "fast-diff", "journaling"))
_MUTABLE_FEATURES_DISABLE = frozenset(
    ("exclusive-lock", "object-map", "fast-diff", "deep-flatten", "journaling")
)


def __virtual__():
    required = {
        "ceph_rbd.get",
        "ceph_rbd.create",
        "ceph_rbd.update",
        "ceph_rbd.delete",
        "ceph_rbd.namespace_list",
        "ceph_rbd.namespace_create",
        "ceph_rbd.namespace_delete",
        "ceph_rbd.snapshot_create",
        "ceph_rbd.snapshot_update",
        "ceph_rbd.snapshot_delete",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _not_found(exc):
    info = getattr(exc, "info", None)
    return isinstance(info, Mapping) and info.get("status") == 404


def _parts(image_spec):
    image_spec = rbd.validate_image_spec(image_spec)
    parts = image_spec.split("/")
    if len(parts) == 2:
        return parts[0], None, parts[1]
    return parts[0], parts[1], parts[2]


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{label} must be a positive integer.")
    return value


def _optional_layout(obj_size, stripe_unit, stripe_count, data_pool):
    result = {}
    if obj_size is not None:
        obj_size = _positive_integer(obj_size, "obj_size")
        if obj_size & (obj_size - 1):
            raise ConfigurationError("obj_size must be a power of two.")
        result["obj_size"] = obj_size
    if (stripe_unit is None) != (stripe_count is None):
        raise ConfigurationError("stripe_unit and stripe_count must be declared together.")
    if stripe_unit is not None:
        result["stripe_unit"] = _positive_integer(stripe_unit, "stripe_unit")
        result["stripe_count"] = _positive_integer(stripe_count, "stripe_count")
    if data_pool is not None:
        result["data_pool"] = validation.identifier(data_pool, "data_pool")
    return result


def _features(value):
    if value is None:
        return None
    return sorted(
        validation.string_list(
            value,
            "features",
            allowed=rbd.FEATURES,
            optional=False,
        )
    )


def _sensitive_name(value):
    return isinstance(value, str) and any(word in value.upper() for word in _SENSITIVE_WORDS)


def _mapping(value, label, *, configuration=False):
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{label} must be a mapping or null.")
    result = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 255
            or re.search(r"[\x00-\x1f\x7f]", key)
            or (configuration and not _CONFIGURATION_NAME.fullmatch(key))
        ):
            raise ConfigurationError(f"{label} contains an invalid key.")
        if _sensitive_name(key):
            raise ConfigurationError(
                f"{label} with credential-like keys cannot be emitted in state changes."
            )
        if configuration:
            if item is not None and (
                isinstance(item, (list, dict))
                or not isinstance(item, (str, bool, int, float))
                or (isinstance(item, float) and not math.isfinite(item))
            ):
                raise ConfigurationError(f"{label} values must be finite JSON scalars or null.")
            normalized = None if item is None else str(item)
        else:
            if item is not None and not isinstance(item, str):
                raise ConfigurationError(f"{label} values must be strings or null.")
            normalized = item
        if normalized is not None:
            result[key] = normalized
    return result


def _mirror_mode(value):
    if value is None:
        return None
    allowed = set(rbd.MIRROR_MODES).union(("disabled",))
    if not isinstance(value, str) or value not in allowed:
        raise ConfigurationError(
            f"mirror_mode must be one of: {', '.join(sorted(allowed))}, or null."
        )
    return value


def _desired_image(
    image_spec,
    size,
    features,
    obj_size,
    stripe_unit,
    stripe_count,
    data_pool,
    configuration,
    metadata,
    mirror_mode,
):
    pool_name, namespace, image_name = _parts(image_spec)
    desired = {
        "name": image_name,
        "pool_name": pool_name,
        "namespace": namespace,
        "size": _positive_integer(size, "size"),
    }
    desired.update(_optional_layout(obj_size, stripe_unit, stripe_count, data_pool))
    for key, value in {
        "features": _features(features),
        "configuration": _mapping(configuration, "configuration", configuration=True),
        "metadata": _mapping(metadata, "metadata"),
        "mirror_mode": _mirror_mode(mirror_mode),
    }.items():
        if value is not None:
            desired[key] = value
    return desired


def _image(image_spec, profile, omit_usage=False):
    if not isinstance(omit_usage, bool):
        raise ConfigurationError("omit_usage must be a boolean.")
    try:
        item = reconcile.data(
            __salt__["ceph_rbd.get"](
                image_spec,
                omit_usage=omit_usage,
                profile=profile,
            ),
            "Ceph RBD image read",
            expected=Mapping,
        )
    except CommandExecutionError as exc:
        if _not_found(exc):
            return None
        raise
    pool_name, namespace, image_name = _parts(image_spec)
    returned_namespace = item.get("namespace")
    if returned_namespace == "":
        returned_namespace = None
    if (
        item.get("name") != image_name
        or item.get("pool_name") != pool_name
        or returned_namespace != namespace
    ):
        raise ProtocolError("Ceph RBD image response did not match the requested image.")
    return dict(item)


def _configuration_view(value):
    if not isinstance(value, list):
        raise ProtocolError("Ceph RBD image returned invalid configuration data.")
    result = {}
    for entry in value:
        if (
            not isinstance(entry, Mapping)
            or not isinstance(entry.get("name"), str)
            or not isinstance(entry.get("value"), str)
            or entry.get("source") not in (0, 1, 2, "config", "pool", "image")
        ):
            raise ProtocolError("Ceph RBD image returned invalid configuration data.")
        if entry["source"] in (2, "image"):
            if entry["name"] in result:
                raise ProtocolError("Ceph RBD image returned duplicate configuration data.")
            if _sensitive_name(entry["name"]):
                raise ConfigurationError(
                    "Credential-like RBD configuration cannot be emitted in state changes."
                )
            result[entry["name"]] = entry["value"]
    return result


def _metadata_view(value):
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ProtocolError("Ceph RBD image returned invalid metadata.")
    if any(_sensitive_name(key) for key in value):
        raise ConfigurationError("Credential-like RBD metadata cannot be emitted in state changes.")
    return dict(value)


def _image_projection(item, desired):
    if item is None:
        return None
    result = {
        "name": item["name"],
        "pool_name": item["pool_name"],
        "namespace": None if item.get("namespace") == "" else item.get("namespace"),
    }
    for key in desired:
        if key in result:
            continue
        if key in ("size", "obj_size", "stripe_unit", "stripe_count"):
            value = item.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ProtocolError(f"Ceph RBD image returned invalid {key} data.")
            result[key] = value
        elif key == "data_pool":
            if item.get(key) is not None and not isinstance(item.get(key), str):
                raise ProtocolError("Ceph RBD image returned invalid data_pool data.")
            result[key] = item.get(key)
        elif key == "features":
            values = item.get("features_name")
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise ProtocolError("Ceph RBD image returned invalid feature data.")
            result[key] = sorted(values)
        elif key == "configuration":
            result[key] = _configuration_view(item.get(key))
        elif key == "metadata":
            result[key] = _metadata_view(item.get(key))
        elif key == "mirror_mode":
            value = item.get(key)
            if not isinstance(value, str):
                raise ProtocolError("Ceph RBD image returned invalid mirror_mode data.")
            normalized = value.lower()
            if normalized not in set(rbd.MIRROR_MODES).union(("disabled",)):
                raise ProtocolError("Ceph RBD image returned an unknown mirror_mode value.")
            result[key] = normalized
    return result


def _mapping_patch(current, desired):
    return {
        key: desired.get(key)
        for key in sorted(set(current).union(desired))
        if current.get(key) != desired.get(key)
    }


def _image_update(current, desired):
    immutable = ("obj_size", "stripe_unit", "stripe_count", "data_pool")
    drift = [key for key in immutable if key in desired and current.get(key) != desired[key]]
    if drift:
        raise ConfigurationError(
            "Existing RBD image has create-only drift in: " + ", ".join(sorted(drift)) + "."
        )

    update = {}
    destructive = False
    if current["size"] != desired["size"]:
        update["size"] = desired["size"]
        destructive = True
    if "features" in desired and current["features"] != desired["features"]:
        added = set(desired["features"]).difference(current["features"])
        removed = set(current["features"]).difference(desired["features"])
        unsupported = added.difference(_MUTABLE_FEATURES_ENABLE).union(
            removed.difference(_MUTABLE_FEATURES_DISABLE)
        )
        if unsupported:
            raise ConfigurationError(
                "Existing RBD image has feature drift that Dashboard cannot update: "
                + ", ".join(sorted(unsupported))
                + "."
            )
        update["features"] = desired["features"]
    for key in ("configuration", "metadata"):
        if key in desired and current[key] != desired[key]:
            update[key] = _mapping_patch(current[key], desired[key])
    if "mirror_mode" in desired and current["mirror_mode"] != desired["mirror_mode"]:
        before = current["mirror_mode"]
        after = desired["mirror_mode"]
        if before == "disabled":
            update.update(enable_mirror=True, mirror_mode=after)
        elif after == "disabled":
            update["enable_mirror"] = False
            destructive = True
        else:
            update.update(mirror_mode=after, image_mirror_mode=before)
            destructive = True
    return update, destructive


def image_present(
    name,
    size,
    features=None,
    obj_size=None,
    stripe_unit=None,
    stripe_count=None,
    data_pool=None,
    configuration=None,
    metadata=None,
    mirror_mode=None,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
    omit_usage=False,
):
    """Ensure an RBD image has the complete declared, observable fields.

    Set ``omit_usage=True`` to skip the potentially expensive image-usage scan
    on Ceph releases that support it. The default leaves the query parameter
    absent for compatibility with Reef.
    """
    ret = reconcile.state_result(name)
    try:
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        desired = _desired_image(
            name,
            size,
            features,
            obj_size,
            stripe_unit,
            stripe_count,
            data_pool,
            configuration,
            metadata,
            mirror_mode,
        )
        item = _image(name, profile, omit_usage)
        current = _image_projection(item, desired)
        if current == desired:
            return reconcile.no_change(ret, f"RBD image {name} is already current.")
        update = None
        destructive = False
        if item is not None:
            update, destructive = _image_update(current, desired)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"RBD image {name} would be reconciled."
            )
        if destructive and not confirm:
            raise ConfigurationError(
                "Resizing, disabling, or switching RBD image mirroring requires confirm=True."
            )
        if item is None:
            pool_name, namespace, image_name = _parts(name)
            response = __salt__["ceph_rbd.create"](
                image_name,
                pool_name,
                desired["size"],
                namespace=namespace,
                obj_size=desired.get("obj_size"),
                features=desired.get("features"),
                stripe_unit=desired.get("stripe_unit"),
                stripe_count=desired.get("stripe_count"),
                data_pool=desired.get("data_pool"),
                configuration=desired.get("configuration") or None,
                metadata=desired.get("metadata") or None,
                mirror_mode=(
                    None if desired.get("mirror_mode") == "disabled" else desired.get("mirror_mode")
                ),
                profile=profile,
            )
        else:
            response = __salt__["ceph_rbd.update"](
                name,
                confirm=destructive,
                profile=profile,
                **update,
            )
        reconcile.wait_if_accepted(
            __salt__,
            response,
            profile=profile,
            timeout=task_timeout,
            interval=task_interval,
        )
        after = _image_projection(_image(name, profile, omit_usage), desired)
        if after != desired:
            raise ProtocolError(f"RBD image {name} did not converge after mutation.")
        return reconcile.changed(ret, current, after, f"RBD image {name} was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def image_absent(
    name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
    omit_usage=False,
):
    """Ensure an RBD image is absent; permanent deletion requires confirmation.

    Set ``omit_usage=True`` to skip usage collection on supported Ceph releases.
    It remains disabled by default because Reef does not accept that query.
    """
    ret = reconcile.state_result(name)
    try:
        rbd.validate_image_spec(name)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        item = _image(name, profile, omit_usage)
        if item is None:
            return reconcile.no_change(ret, f"RBD image {name} is already absent.")
        current = {
            "name": item["name"],
            "pool_name": item["pool_name"],
            "namespace": None if item.get("namespace") == "" else item.get("namespace"),
        }
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, f"RBD image {name} would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an RBD image requires confirm=True.")
        response = __salt__["ceph_rbd.delete"](name, confirm=True, profile=profile)
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        if _image(name, profile, omit_usage) is not None:
            raise ProtocolError(f"RBD image {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"RBD image {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _namespace(pool_name, namespace, profile):
    items = reconcile.data(
        __salt__["ceph_rbd.namespace_list"](pool_name, profile=profile),
        "Ceph RBD namespace list",
        expected=list,
    )
    matches = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("namespace"), str):
            raise ProtocolError("Ceph RBD namespace list returned an unexpected response shape.")
        count = item.get("num_images")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ProtocolError("Ceph RBD namespace list returned an unexpected response shape.")
        item_name = item["namespace"]
        if item_name in seen:
            raise ProtocolError("Ceph RBD namespace list returned duplicate namespaces.")
        seen.add(item_name)
        if item_name == namespace:
            matches.append({"pool_name": pool_name, "namespace": namespace, "num_images": count})
    return matches[0] if matches else None


def namespace_present(name, pool_name, profile="default", task_timeout=300.0, task_interval=2.0):
    """Ensure ``name`` exists as an RBD namespace in ``pool_name``."""
    ret = reconcile.state_result(name)
    try:
        pool_name = validation.identifier(pool_name, "pool_name")
        name = validation.identifier(name, "namespace")
        desired = {"pool_name": pool_name, "namespace": name}
        resource = _namespace(pool_name, name, profile)
        current = None if resource is None else desired
        if current == desired:
            return reconcile.no_change(ret, f"RBD namespace {pool_name}/{name} already exists.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"RBD namespace {pool_name}/{name} would be created."
            )
        response = __salt__["ceph_rbd.namespace_create"](pool_name, name, profile=profile)
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        if _namespace(pool_name, name, profile) is None:
            raise ProtocolError(f"RBD namespace {pool_name}/{name} did not appear after creation.")
        return reconcile.changed(
            ret, current, desired, f"RBD namespace {pool_name}/{name} was created."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def namespace_absent(
    name,
    pool_name,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure an empty RBD namespace is absent; deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        pool_name = validation.identifier(pool_name, "pool_name")
        name = validation.identifier(name, "namespace")
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        resource = _namespace(pool_name, name, profile)
        if resource is None:
            return reconcile.no_change(ret, f"RBD namespace {pool_name}/{name} is already absent.")
        current = {"pool_name": pool_name, "namespace": name}
        if not isinstance(resource, Mapping):
            raise ProtocolError("Ceph RBD namespace read returned invalid data.")
        resource = dict(resource)
        if resource["num_images"]:
            raise ConfigurationError("An RBD namespace must be empty before it can be deleted.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"RBD namespace {pool_name}/{name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting an RBD namespace requires confirm=True.")
        response = __salt__["ceph_rbd.namespace_delete"](
            pool_name, name, confirm=True, profile=profile
        )
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        if _namespace(pool_name, name, profile) is not None:
            raise ProtocolError(f"RBD namespace {pool_name}/{name} still exists after deletion.")
        return reconcile.changed(
            ret, current, None, f"RBD namespace {pool_name}/{name} was deleted."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _snapshot(item, snapshot_name, manage_protection):
    if not isinstance(item, Mapping):
        raise ProtocolError("Parent RBD image disappeared while reading snapshots.")
    snapshots = item.get("snapshots")
    if not isinstance(snapshots, list):
        raise ProtocolError("Ceph RBD image returned invalid snapshot data.")
    matches = []
    seen = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("name"), str):
            raise ProtocolError("Ceph RBD image returned invalid snapshot data.")
        item_name = snapshot["name"]
        if item_name in seen:
            raise ProtocolError("Ceph RBD image returned duplicate snapshots.")
        seen.add(item_name)
        if item_name == snapshot_name:
            current = {"name": snapshot_name}
            if manage_protection:
                protected = snapshot.get("is_protected")
                if protected is not None and not isinstance(protected, bool):
                    raise ProtocolError("Ceph RBD image returned invalid snapshot protection data.")
                current["is_protected"] = protected
            matches.append(current)
    return matches[0] if matches else None


def snapshot_present(
    name,
    image_spec,
    is_protected=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
    omit_usage=False,
):
    """Ensure an image snapshot exists and optionally manage protection.

    Snapshots are read through their parent image. Set ``omit_usage=True`` to
    avoid its usage scan on supported releases; the Reef-compatible default
    leaves the query parameter absent.
    """
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "snapshot_name")
        rbd.validate_image_spec(image_spec)
        if is_protected is not None and not isinstance(is_protected, bool):
            raise ConfigurationError("is_protected must be a boolean or null.")
        desired = {"name": name}
        if is_protected is not None:
            desired["is_protected"] = is_protected
        image = _image(image_spec, profile, omit_usage)
        if image is None:
            raise ConfigurationError(f"Parent RBD image {image_spec} does not exist.")
        current = _snapshot(image, name, is_protected is not None)
        before = current
        if current == desired:
            return reconcile.no_change(ret, f"RBD snapshot {image_spec}@{name} is already current.")
        if current is not None and current.get("is_protected") is None:
            raise ConfigurationError("Mirroring snapshots do not support protection changes.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, desired, f"RBD snapshot {image_spec}@{name} would be reconciled."
            )
        if current is None:
            response = __salt__["ceph_rbd.snapshot_create"](
                image_spec, name, mirror_image_snapshot=False, profile=profile
            )
            reconcile.wait_if_accepted(
                __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
            )
            image = _image(image_spec, profile, omit_usage)
            current_after_create = _snapshot(image, name, is_protected is not None)
            if current_after_create is None:
                raise ProtocolError(
                    f"RBD snapshot {image_spec}@{name} did not appear after creation."
                )
            current = current_after_create
        if not isinstance(current, Mapping):
            raise ProtocolError(
                f"RBD snapshot {image_spec}@{name} disappeared during reconciliation."
            )
        current = dict(current)
        if is_protected is not None and current["is_protected"] != is_protected:
            response = __salt__["ceph_rbd.snapshot_update"](
                image_spec, name, is_protected=is_protected, profile=profile
            )
            reconcile.wait_if_accepted(
                __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
            )
        after_image = _image(image_spec, profile, omit_usage)
        after = _snapshot(after_image, name, is_protected is not None)
        if after != desired:
            raise ProtocolError(f"RBD snapshot {image_spec}@{name} did not converge.")
        return reconcile.changed(
            ret,
            before,
            after,
            f"RBD snapshot {image_spec}@{name} was reconciled.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def snapshot_absent(
    name,
    image_spec,
    confirm=False,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
    omit_usage=False,
):
    """Ensure an image snapshot is absent; deletion requires confirmation.

    Set ``omit_usage=True`` to skip parent-image usage collection on supported
    Ceph releases. The default remains compatible with Reef.
    """
    ret = reconcile.state_result(name)
    try:
        name = validation.identifier(name, "snapshot_name")
        rbd.validate_image_spec(image_spec)
        if not isinstance(confirm, bool):
            raise ConfigurationError("confirm must be a boolean.")
        image = _image(image_spec, profile, omit_usage)
        current = None if image is None else _snapshot(image, name, False)
        if current is None:
            return reconcile.no_change(ret, f"RBD snapshot {image_spec}@{name} is already absent.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret, current, None, f"RBD snapshot {image_spec}@{name} would be deleted."
            )
        if not confirm:
            raise ConfigurationError("Deleting an RBD snapshot requires confirm=True.")
        response = __salt__["ceph_rbd.snapshot_delete"](
            image_spec, name, confirm=True, profile=profile
        )
        reconcile.wait_if_accepted(
            __salt__, response, profile=profile, timeout=task_timeout, interval=task_interval
        )
        after_image = _image(image_spec, profile, omit_usage)
        if after_image is not None and _snapshot(after_image, name, False) is not None:
            raise ProtocolError(f"RBD snapshot {image_spec}@{name} still exists after deletion.")
        return reconcile.changed(
            ret, current, None, f"RBD snapshot {image_spec}@{name} was deleted."
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
