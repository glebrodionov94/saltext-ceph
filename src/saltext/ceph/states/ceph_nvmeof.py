"""Declaratively manage public Ceph Dashboard NVMe-oF resources."""

from collections.abc import Mapping
from collections.abc import Sequence

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph import nvmeof
from saltext.ceph.utils.ceph import nvmeof_gateway
from saltext.ceph.utils.ceph import reconcile
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError
from saltext.ceph.utils.ceph.errors import ProtocolError

__virtualname__ = "ceph_nvmeof"
_ERRORS = (CephError, CommandExecutionError, SaltInvocationError)
_QOS_FIELDS = (
    "rw_ios_per_second",
    "rw_mbytes_per_second",
    "r_mbytes_per_second",
    "w_mbytes_per_second",
)
_IMMUTABLE_NAMESPACE_FIELDS = frozenset(
    (
        "rbd_image_name",
        "rbd_pool_name",
        "rbd_data_pool_name",
        "rados_namespace_name",
        "uuid",
        "block_size",
        "read_only",
        "encryption_entries",
    )
)


def __virtual__():
    required = {
        "ceph_nvmeof.gateway_info",
        "ceph_nvmeof.gateway_log_level",
        "ceph_nvmeof.gateway_set_io_stats",
        "ceph_nvmeof.gateway_set_log_level",
        "ceph_nvmeof.subsystem_get",
        "ceph_nvmeof.subsystem_create",
        "ceph_nvmeof.subsystem_delete",
        "ceph_nvmeof.subsystem_change_key",
        "ceph_nvmeof.listener_list",
        "ceph_nvmeof.listener_create",
        "ceph_nvmeof.listener_delete",
        "ceph_nvmeof.host_list",
        "ceph_nvmeof.host_create",
        "ceph_nvmeof.host_delete",
        "ceph_nvmeof.host_change_key",
        "ceph_nvmeof.host_change_controller_key",
        "ceph_nvmeof.namespace_get",
        "ceph_nvmeof.namespace_create",
        "ceph_nvmeof.namespace_delete",
        "ceph_nvmeof.namespace_resize",
        "ceph_nvmeof.namespace_set_qos",
        "ceph_nvmeof.namespace_change_load_balancing_group",
        "ceph_nvmeof.namespace_unpin",
        "ceph_nvmeof.namespace_change_visibility",
        "ceph_nvmeof.namespace_change_location",
        "ceph_nvmeof.namespace_set_auto_resize",
        "ceph_nvmeof.namespace_set_rbd_trash_image",
        "ceph_nvmeof.namespace_add_host",
        "ceph_nvmeof.namespace_delete_host",
    }
    missing = sorted(required.difference(__salt__))
    if missing:
        return False, f"Missing execution functions: {', '.join(missing)}"
    return __virtualname__


def _not_found(exc):
    info = getattr(exc, "info", None)
    return isinstance(info, Mapping) and info.get("status") == 404


def _boolean(value, label):
    return nvmeof.boolean(value, label)


def _routing(gw_group, server_address, routing_traddr):
    return nvmeof.routing(gw_group, server_address, routing_traddr)


def _wait(response, profile, timeout, interval):
    return reconcile.wait_if_accepted(
        __salt__,
        response,
        profile=profile,
        timeout=timeout,
        interval=interval,
    )


def _validate_secret_source(source):
    if source is not None:
        secret_file.read(source)


def _optional_identifier(value, label):
    return None if value is None else nvmeof.identifier(value, label)


def _optional_text(value, label, *, max_length=255, empty_as_none=False):
    if value is None:
        return None
    value = nvmeof.text(
        value,
        label,
        allow_empty=empty_as_none,
        max_length=max_length,
    )
    return None if empty_as_none and value == "" else value


def _optional_integer(value, label, *, minimum=0, maximum=nvmeof.MAX_UINT32):
    if value is None:
        return None
    return nvmeof.integer(value, label, minimum=minimum, maximum=maximum)


def _network_list(value):
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError("network_mask must be a list.")
    result = [nvmeof.network(item, "network_mask") for item in value]
    if len(set(result)) != len(result):
        raise ConfigurationError("network_mask must not contain duplicate networks.")
    return sorted(result)


def _string_field(item, key, label, *, optional=False, empty_as_none=False):
    value = item.get(key)
    if value is None and optional:
        return None
    if value is None:
        raise ProtocolError(f"Ceph NVMe-oF returned invalid {label} data.")
    try:
        return _optional_text(
            value,
            label,
            max_length=4096,
            empty_as_none=empty_as_none,
        )
    except ConfigurationError as exc:
        raise ProtocolError(f"Ceph NVMe-oF returned invalid {label} data.") from exc


def _integer_field(item, key, label, *, minimum=0, maximum=nvmeof.MAX_UINT32):
    try:
        return nvmeof.integer(item.get(key), label, minimum=minimum, maximum=maximum)
    except ConfigurationError as exc:
        raise ProtocolError(f"Ceph NVMe-oF returned invalid {label} data.") from exc


def _boolean_field(item, key, label, *, optional=False):
    value = item.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, bool):
        raise ProtocolError(f"Ceph NVMe-oF returned invalid {label} data.")
    return value


def _gateway_desired(log_level, io_stats_enabled):
    desired = {}
    if log_level is not None:
        if (
            not isinstance(log_level, str)
            or log_level.strip().lower() not in nvmeof_gateway.GATEWAY_LOG_LEVELS
        ):
            raise ConfigurationError(
                "log_level must be one of: "
                + ", ".join(sorted(nvmeof_gateway.GATEWAY_LOG_LEVELS))
                + "."
            )
        desired["log_level"] = log_level.strip().lower()
    if io_stats_enabled is not None:
        desired["io_stats_enabled"] = _boolean(io_stats_enabled, "io_stats_enabled")
    if not desired:
        raise ConfigurationError("At least one gateway setting must be declared.")
    return desired


def _gateway_current(desired, route, profile):
    current = {}
    if "log_level" in desired:
        item = reconcile.data(
            __salt__["ceph_nvmeof.gateway_log_level"](profile=profile, **route),
            "Ceph NVMe-oF gateway log-level read",
            expected=Mapping,
        )
        value = item.get("log_level")
        if (
            not isinstance(value, str)
            or value.strip().lower() not in nvmeof_gateway.GATEWAY_LOG_LEVELS
        ):
            raise ProtocolError("Ceph NVMe-oF gateway returned an invalid log level.")
        current["log_level"] = value.strip().lower()
    if "io_stats_enabled" in desired:
        item = reconcile.data(
            __salt__["ceph_nvmeof.gateway_info"](profile=profile, **route),
            "Ceph NVMe-oF gateway information read",
            expected=Mapping,
        )
        current["io_stats_enabled"] = _boolean_field(
            item,
            "io_stats_enabled",
            "io_stats_enabled",
        )
    return current


def gateway_configured(
    name,
    log_level=None,
    io_stats_enabled=None,
    gw_group=None,
    server_address=None,
    routing_traddr=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure exact GET-backed settings on one explicitly addressed gateway."""
    ret = reconcile.state_result(name)
    try:
        route = nvmeof.routing(
            gw_group,
            server_address,
            routing_traddr,
            require_address=True,
        )
        desired = _gateway_desired(log_level, io_stats_enabled)
        current = _gateway_current(desired, route, profile)
        if current == desired:
            return reconcile.no_change(ret, f"NVMe-oF gateway {name} is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                desired,
                f"NVMe-oF gateway {name} would be reconciled.",
            )
        if current.get("log_level") != desired.get("log_level") and "log_level" in desired:
            _wait(
                __salt__["ceph_nvmeof.gateway_set_log_level"](
                    desired["log_level"],
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )
        if (
            current.get("io_stats_enabled") != desired.get("io_stats_enabled")
            and "io_stats_enabled" in desired
        ):
            _wait(
                __salt__["ceph_nvmeof.gateway_set_io_stats"](
                    desired["io_stats_enabled"],
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )
        after = _gateway_current(desired, route, profile)
        if after != desired:
            raise ProtocolError(f"NVMe-oF gateway {name} did not converge after mutation.")
        return reconcile.changed(
            ret,
            current,
            after,
            f"NVMe-oF gateway {name} was reconciled.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _subsystem_desired(
    name,
    serial_number,
    model_name,
    max_namespaces,
    network_mask,
    dhchap_key_source,
):
    desired = {"nqn": nvmeof.nqn(name)}
    optional = {
        "serial_number": (
            _optional_text(serial_number, "serial_number", max_length=64)
            if serial_number is not None
            else None
        ),
        "model_number": (
            _optional_text(model_name, "model_name", max_length=64)
            if model_name is not None
            else None
        ),
        "max_namespaces": _optional_integer(
            max_namespaces,
            "max_namespaces",
            minimum=1,
        ),
        "network_mask": _network_list(network_mask),
    }
    desired.update({key: value for key, value in optional.items() if value is not None})
    if dhchap_key_source is not None:
        desired["has_dhchap_key"] = True
    return desired


def _subsystem(name, route, profile):
    try:
        item = reconcile.data(
            __salt__["ceph_nvmeof.subsystem_get"](name, profile=profile, **route),
            "Ceph NVMe-oF subsystem read",
            expected=Mapping,
        )
    except CommandExecutionError as exc:
        if _not_found(exc):
            return None
        raise
    if item.get("nqn") != name:
        raise ProtocolError("Ceph NVMe-oF subsystem response did not match the requested NQN.")
    return dict(item)


def _subsystem_projection(item, desired):
    if item is None:
        return None
    result = {"nqn": item.get("nqn")}
    for key in desired:
        if key == "nqn":
            continue
        if key in ("serial_number", "model_number"):
            result[key] = _string_field(item, key, key)
        elif key == "max_namespaces":
            result[key] = _integer_field(item, key, key, minimum=1)
        elif key == "network_mask":
            value = item.get(key)
            if not isinstance(value, list):
                raise ProtocolError("Ceph NVMe-oF returned invalid network_mask data.")
            try:
                result[key] = _network_list(value)
            except ConfigurationError as exc:
                raise ProtocolError("Ceph NVMe-oF returned invalid network_mask data.") from exc
        elif key == "has_dhchap_key":
            result[key] = _boolean_field(item, key, key)
    return result


def _subsystem_delete_view(item):
    return {
        "nqn": item["nqn"],
        "namespace_count": _integer_field(item, "namespace_count", "namespace_count"),
    }


def _subsystem_replacement_values(item, desired):
    """Preserve observable create-only fields omitted from a declaration."""
    result = dict(desired)
    for key in ("serial_number", "model_number", "max_namespaces", "network_mask"):
        if key not in result:
            result[key] = _subsystem_projection(item, {"nqn": item["nqn"], key: None})[key]
    return result


def subsystem_present(
    name,
    serial_number=None,
    model_name=None,
    max_namespaces=None,
    network_mask=None,
    dhchap_key_source=None,
    confirm=False,
    confirm_replace=False,
    gw_group=None,
    server_address=None,
    routing_traddr=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a subsystem has the declared observable fields.

    Existing key material is never read or compared. ``dhchap_key_source``
    means that a key must be present; a missing key is installed only with
    ``confirm=True``. Create-only field drift requires an empty subsystem and
    ``confirm_replace=True``.
    """
    ret = reconcile.state_result(name)
    try:
        _boolean(confirm, "confirm")
        _boolean(confirm_replace, "confirm_replace")
        route = _routing(gw_group, server_address, routing_traddr)
        desired = _subsystem_desired(
            name,
            serial_number,
            model_name,
            max_namespaces,
            network_mask,
            dhchap_key_source,
        )
        item = _subsystem(name, route, profile)
        current = _subsystem_projection(item, desired)
        if current == desired:
            return reconcile.no_change(ret, f"NVMe-oF subsystem {name} is already current.")

        immutable_drift = []
        missing_key = False
        creation = desired
        if item is not None:
            immutable_drift = sorted(
                key
                for key, wanted in desired.items()
                if key not in ("nqn", "has_dhchap_key") and current.get(key) != wanted
            )
            missing_key = desired.get("has_dhchap_key") is True and not current.get(
                "has_dhchap_key"
            )
            if immutable_drift:
                creation = _subsystem_replacement_values(item, desired)
                has_key = _boolean_field(item, "has_dhchap_key", "has_dhchap_key")
                if has_key and dhchap_key_source is None:
                    raise ConfigurationError(
                        "dhchap_key_source is required to preserve the subsystem key during "
                        "replacement."
                    )
        source_needed = item is None or bool(immutable_drift) or missing_key
        if source_needed:
            _validate_secret_source(dhchap_key_source)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                desired,
                f"NVMe-oF subsystem {name} would be reconciled.",
            )

        if immutable_drift:
            if not confirm_replace:
                raise ConfigurationError(
                    "Replacing a subsystem with create-only drift requires confirm_replace=True."
                )
            namespace_count = _integer_field(
                item,
                "namespace_count",
                "namespace_count",
            )
            if namespace_count:
                raise ConfigurationError(
                    "A subsystem with namespaces cannot be replaced by this state."
                )
            _wait(
                __salt__["ceph_nvmeof.subsystem_delete"](
                    name,
                    force=False,
                    confirm=True,
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )
            if _subsystem(name, route, profile) is not None:
                raise ProtocolError(f"NVMe-oF subsystem {name} still exists after deletion.")
            item = None
        elif missing_key:
            if not confirm:
                raise ConfigurationError(
                    "Installing an NVMe-oF subsystem key requires confirm=True."
                )
            _wait(
                __salt__["ceph_nvmeof.subsystem_change_key"](
                    name,
                    dhchap_key_source,
                    confirm=True,
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )

        if item is None:
            _wait(
                __salt__["ceph_nvmeof.subsystem_create"](
                    name,
                    max_namespaces=creation.get("max_namespaces"),
                    serial_number=creation.get("serial_number"),
                    dhchap_key_source=dhchap_key_source,
                    network_mask=creation.get("network_mask") or None,
                    model_name=creation.get("model_number"),
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )
        after = _subsystem_projection(_subsystem(name, route, profile), desired)
        if after != desired:
            raise ProtocolError(f"NVMe-oF subsystem {name} did not converge after mutation.")
        return reconcile.changed(
            ret,
            current,
            after,
            f"NVMe-oF subsystem {name} was reconciled.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def subsystem_absent(
    name,
    force=False,
    confirm=False,
    gw_group=None,
    server_address=None,
    routing_traddr=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a subsystem is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        name = nvmeof.nqn(name)
        _boolean(force, "force")
        _boolean(confirm, "confirm")
        route = _routing(gw_group, server_address, routing_traddr)
        item = _subsystem(name, route, profile)
        if item is None:
            return reconcile.no_change(ret, f"NVMe-oF subsystem {name} is already absent.")
        current = _subsystem_delete_view(item)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                None,
                f"NVMe-oF subsystem {name} would be deleted.",
            )
        if not confirm:
            raise ConfigurationError("Deleting an NVMe-oF subsystem requires confirm=True.")
        _wait(
            __salt__["ceph_nvmeof.subsystem_delete"](
                name,
                force=force,
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            task_timeout,
            task_interval,
        )
        if _subsystem(name, route, profile) is not None:
            raise ProtocolError(f"NVMe-oF subsystem {name} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"NVMe-oF subsystem {name} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _listener_view(item):
    if not isinstance(item, Mapping):
        raise ProtocolError("Ceph NVMe-oF listener list returned invalid data.")
    try:
        host_name = item.get("host_name")
        if host_name != "*":
            host_name = nvmeof.identifier(host_name, "host_name")
        address = nvmeof.ip_address(item.get("traddr"))
        adrfam = nvmeof.address_family(item.get("adrfam"), address)
        trsvcid = nvmeof.port(item.get("trsvcid"), "trsvcid")
    except ConfigurationError as exc:
        raise ProtocolError("Ceph NVMe-oF listener list returned invalid data.") from exc
    secure = _boolean_field(item, "secure", "listener secure", optional=True)
    manual = _boolean_field(item, "manual", "listener manual", optional=True)
    return {
        "host_name": host_name,
        "traddr": address,
        "trsvcid": trsvcid,
        "adrfam": adrfam,
        "secure": secure,
        "manual": manual,
    }


def _listeners(nqn, route, profile):
    items = reconcile.data(
        __salt__["ceph_nvmeof.listener_list"](nqn, profile=profile, **route),
        "Ceph NVMe-oF listener list",
        expected=list,
    )
    result = [_listener_view(item) for item in items]
    identities = [(item["host_name"], item["traddr"], item["trsvcid"]) for item in result]
    if len(set(identities)) != len(identities):
        raise ProtocolError("Ceph NVMe-oF listener list returned duplicate resources.")
    return result


def _listener(nqn, desired, route, profile):
    matches = [
        item
        for item in _listeners(nqn, route, profile)
        if (item["host_name"], item["traddr"], item["trsvcid"])
        == (desired["host_name"], desired["traddr"], desired["trsvcid"])
    ]
    return matches[0] if matches else None


def _listener_desired(host_name, traddr, trsvcid, adrfam, secure, *, wildcard=False):
    if wildcard and host_name == "*":
        normalized_host = host_name
    else:
        normalized_host = nvmeof.identifier(host_name, "host_name")
    address = nvmeof.ip_address(traddr)
    return {
        "host_name": normalized_host,
        "traddr": address,
        "trsvcid": nvmeof.port(trsvcid, "trsvcid"),
        "adrfam": nvmeof.address_family(adrfam, address),
        "secure": _boolean(secure, "secure"),
    }


def listener_present(
    name,
    host_name,
    traddr,
    trsvcid=4420,
    adrfam=0,
    secure=False,
    confirm_replace=False,
    gw_group=None,
    server_address=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure one manually addressed listener has the declared GET fields.

    ``name`` is the subsystem NQN. Drift in ``secure`` is repaired through a
    confirmed delete/create replacement because Dashboard has no listener
    update endpoint.
    """
    ret = reconcile.state_result(name)
    try:
        nqn = nvmeof.nqn(name)
        _boolean(confirm_replace, "confirm_replace")
        route = nvmeof.routing(gw_group, server_address)
        desired = _listener_desired(host_name, traddr, trsvcid, adrfam, secure)
        item = _listener(nqn, desired, route, profile)
        current = None if item is None else reconcile.project(item, desired)
        if current == desired:
            return reconcile.no_change(ret, "NVMe-oF listener is already current.")
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, desired, "NVMe-oF listener would be reconciled.")
        if item is not None:
            if not confirm_replace:
                raise ConfigurationError(
                    "Replacing an NVMe-oF listener requires confirm_replace=True."
                )
            _wait(
                __salt__["ceph_nvmeof.listener_delete"](
                    nqn,
                    item["host_name"],
                    item["traddr"],
                    item["trsvcid"],
                    adrfam=item["adrfam"],
                    force=False,
                    confirm=True,
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )
            if _listener(nqn, desired, route, profile) is not None:
                raise ProtocolError("NVMe-oF listener still exists after deletion.")
        _wait(
            __salt__["ceph_nvmeof.listener_create"](
                nqn,
                desired["host_name"],
                desired["traddr"],
                trsvcid=desired["trsvcid"],
                adrfam=desired["adrfam"],
                secure=desired["secure"],
                profile=profile,
                **route,
            ),
            profile,
            task_timeout,
            task_interval,
        )
        after_item = _listener(nqn, desired, route, profile)
        after = None if after_item is None else reconcile.project(after_item, desired)
        if after != desired:
            raise ProtocolError("NVMe-oF listener did not converge after mutation.")
        return reconcile.changed(ret, current, after, "NVMe-oF listener was reconciled.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def listener_absent(
    name,
    host_name,
    traddr,
    trsvcid=4420,
    adrfam=0,
    force=False,
    confirm=False,
    gw_group=None,
    server_address=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure one listener is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        nqn = nvmeof.nqn(name)
        _boolean(force, "force")
        _boolean(confirm, "confirm")
        route = nvmeof.routing(gw_group, server_address)
        desired = _listener_desired(
            host_name,
            traddr,
            trsvcid,
            adrfam,
            False,
            wildcard=True,
        )
        item = _listener(nqn, desired, route, profile)
        if item is None:
            return reconcile.no_change(ret, "NVMe-oF listener is already absent.")
        current = {key: item[key] for key in ("host_name", "traddr", "trsvcid", "adrfam", "secure")}
        if __opts__.get("test", False):
            return reconcile.planned(ret, current, None, "NVMe-oF listener would be deleted.")
        if not confirm:
            raise ConfigurationError("Deleting an NVMe-oF listener requires confirm=True.")
        _wait(
            __salt__["ceph_nvmeof.listener_delete"](
                nqn,
                item["host_name"],
                item["traddr"],
                item["trsvcid"],
                adrfam=item["adrfam"],
                force=force,
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            task_timeout,
            task_interval,
        )
        if _listener(nqn, desired, route, profile) is not None:
            raise ProtocolError("NVMe-oF listener still exists after deletion.")
        return reconcile.changed(ret, current, None, "NVMe-oF listener was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _host_view(item):
    if not isinstance(item, Mapping):
        raise ProtocolError("Ceph NVMe-oF host list returned invalid data.")
    try:
        host_nqn = nvmeof.nqn(item.get("nqn"), "host_nqn", wildcard=True)
    except ConfigurationError as exc:
        raise ProtocolError("Ceph NVMe-oF host list returned invalid data.") from exc
    result = {"nqn": host_nqn}
    for key in ("use_psk", "use_dhchap"):
        result[key] = _boolean_field(item, key, key, optional=True)
    origin = item.get("dhchap_controller_origin")
    if origin not in (None, "No Key", "Host Specific", "Subsystem Implicit"):
        raise ProtocolError("Ceph NVMe-oF host list returned invalid controller-key origin.")
    result["dhchap_controller_origin"] = origin
    return result


def _hosts(nqn, route, profile):
    items = reconcile.data(
        __salt__["ceph_nvmeof.host_list"](nqn, profile=profile, **route),
        "Ceph NVMe-oF host list",
        expected=list,
    )
    result = [_host_view(item) for item in items]
    names = [item["nqn"] for item in result]
    if len(set(names)) != len(names):
        raise ProtocolError("Ceph NVMe-oF host list returned duplicate resources.")
    return result


def _host(nqn, host_nqn, route, profile):
    return next((item for item in _hosts(nqn, route, profile) if item["nqn"] == host_nqn), None)


def _host_desired(name, dhchap_key_source, dhchap_controller_key_source, psk_source):
    host_nqn = nvmeof.nqn(name, "host_nqn", wildcard=True)
    if host_nqn == "*" and any(
        source is not None
        for source in (dhchap_key_source, dhchap_controller_key_source, psk_source)
    ):
        raise ConfigurationError("Wildcard host access cannot carry authentication keys.")
    desired = {"nqn": host_nqn}
    if dhchap_key_source is not None:
        desired["use_dhchap"] = True
    if dhchap_controller_key_source is not None:
        desired["dhchap_controller_origin"] = "Host Specific"
    if psk_source is not None:
        desired["use_psk"] = True
    return desired


def host_present(
    name,
    subsystem_nqn,
    dhchap_key_source=None,
    dhchap_controller_key_source=None,
    psk_source=None,
    confirm=False,
    confirm_replace=False,
    gw_group=None,
    server_address=None,
    routing_traddr=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a host allowlist entry and declared key-presence flags exist.

    Source files are used for creation or to install a missing key. Existing
    secret values cannot be compared and are never rotated merely because a
    source path was declared. TLS-PSK is create-only in the public API, so
    repairing missing PSK presence requires ``confirm_replace=True``.
    """
    ret = reconcile.state_result(name)
    try:
        subsystem_nqn = nvmeof.nqn(subsystem_nqn, "subsystem_nqn")
        _boolean(confirm, "confirm")
        _boolean(confirm_replace, "confirm_replace")
        route = _routing(gw_group, server_address, routing_traddr)
        desired = _host_desired(
            name,
            dhchap_key_source,
            dhchap_controller_key_source,
            psk_source,
        )
        host_nqn = desired["nqn"]
        item = _host(subsystem_nqn, host_nqn, route, profile)
        current = None if item is None else reconcile.project(item, desired)
        if current == desired:
            return reconcile.no_change(ret, f"NVMe-oF host {host_nqn} is already current.")
        missing_dhchap = (
            item is not None and desired.get("use_dhchap") is True and not item.get("use_dhchap")
        )
        missing_controller = (
            item is not None
            and desired.get("dhchap_controller_origin") == "Host Specific"
            and item.get("dhchap_controller_origin") != "Host Specific"
        )
        missing_psk = (
            item is not None and desired.get("use_psk") is True and not item.get("use_psk")
        )
        required_sources = []
        if item is None or missing_dhchap:
            required_sources.append(dhchap_key_source)
        if item is None or missing_controller:
            required_sources.append(dhchap_controller_key_source)
        if item is None or missing_psk:
            required_sources.append(psk_source)
        if __opts__.get("test", False):
            for source in required_sources:
                _validate_secret_source(source)
            return reconcile.planned(
                ret,
                current,
                desired,
                f"NVMe-oF host {host_nqn} would be reconciled.",
            )
        for source in required_sources:
            _validate_secret_source(source)
        if missing_psk:
            if not confirm_replace:
                raise ConfigurationError(
                    "Replacing an NVMe-oF host to install TLS-PSK requires confirm_replace=True."
                )
            if item.get("use_dhchap") is True and dhchap_key_source is None:
                raise ConfigurationError(
                    "dhchap_key_source is required to preserve host DHCHAP during replacement."
                )
            if (
                item.get("dhchap_controller_origin") == "Host Specific"
                and dhchap_controller_key_source is None
            ):
                raise ConfigurationError(
                    "dhchap_controller_key_source is required to preserve the host-specific "
                    "controller key during replacement."
                )
            _wait(
                __salt__["ceph_nvmeof.host_delete"](
                    subsystem_nqn,
                    host_nqn,
                    force=False,
                    keep_connections=False,
                    confirm=True,
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )
            if _host(subsystem_nqn, host_nqn, route, profile) is not None:
                raise ProtocolError(f"NVMe-oF host {host_nqn} still exists after deletion.")
            item = None
        elif missing_dhchap or missing_controller:
            if not confirm:
                raise ConfigurationError("Installing an NVMe-oF host key requires confirm=True.")
            if missing_dhchap:
                _wait(
                    __salt__["ceph_nvmeof.host_change_key"](
                        subsystem_nqn,
                        host_nqn,
                        dhchap_key_source,
                        confirm=True,
                        profile=profile,
                        **route,
                    ),
                    profile,
                    task_timeout,
                    task_interval,
                )
            if missing_controller:
                _wait(
                    __salt__["ceph_nvmeof.host_change_controller_key"](
                        subsystem_nqn,
                        host_nqn,
                        dhchap_controller_key_source,
                        confirm=True,
                        profile=profile,
                        **route,
                    ),
                    profile,
                    task_timeout,
                    task_interval,
                )
        if item is None:
            _wait(
                __salt__["ceph_nvmeof.host_create"](
                    subsystem_nqn,
                    host_nqn,
                    dhchap_key_source=dhchap_key_source,
                    dhchap_controller_key_source=dhchap_controller_key_source,
                    psk_source=psk_source,
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )
        after_item = _host(subsystem_nqn, host_nqn, route, profile)
        after = None if after_item is None else reconcile.project(after_item, desired)
        if after != desired:
            raise ProtocolError(f"NVMe-oF host {host_nqn} did not converge after mutation.")
        return reconcile.changed(
            ret,
            current,
            after,
            f"NVMe-oF host {host_nqn} was reconciled.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def host_absent(
    name,
    subsystem_nqn,
    force=False,
    keep_connections=False,
    confirm=False,
    gw_group=None,
    server_address=None,
    routing_traddr=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a host allowlist entry is absent; deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        host_nqn = nvmeof.nqn(name, "host_nqn", wildcard=True)
        subsystem_nqn = nvmeof.nqn(subsystem_nqn, "subsystem_nqn")
        _boolean(force, "force")
        _boolean(keep_connections, "keep_connections")
        _boolean(confirm, "confirm")
        route = _routing(gw_group, server_address, routing_traddr)
        item = _host(subsystem_nqn, host_nqn, route, profile)
        if item is None:
            return reconcile.no_change(ret, f"NVMe-oF host {host_nqn} is already absent.")
        current = dict(item)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                None,
                f"NVMe-oF host {host_nqn} would be deleted.",
            )
        if not confirm:
            raise ConfigurationError("Deleting an NVMe-oF host requires confirm=True.")
        _wait(
            __salt__["ceph_nvmeof.host_delete"](
                subsystem_nqn,
                host_nqn,
                force=force,
                keep_connections=keep_connections,
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            task_timeout,
            task_interval,
        )
        if _host(subsystem_nqn, host_nqn, route, profile) is not None:
            raise ProtocolError(f"NVMe-oF host {host_nqn} still exists after deletion.")
        return reconcile.changed(ret, current, None, f"NVMe-oF host {host_nqn} was deleted.")
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def _encryption_entries(formats, key_ids):
    if formats is None and key_ids is None:
        return []
    if formats is None or key_ids is None:
        raise ConfigurationError("encryption_format and key_id must be declared together.")
    normalized_formats = nvmeof.string_list(
        formats,
        "encryption_format",
        allowed={"LUKS1", "LUKS2"},
        optional=False,
    )
    normalized_ids = nvmeof.string_list(key_ids, "key_id", optional=False)
    if len(normalized_formats) != len(normalized_ids):
        raise ConfigurationError("The number of key_id values must match encryption_format values.")
    entries = [
        {"format": fmt.upper(), "key_id": key_id}
        for fmt, key_id in zip(normalized_formats, normalized_ids)
    ]
    if len({(item["format"], item["key_id"]) for item in entries}) != len(entries):
        raise ConfigurationError("Encryption entries must not contain duplicates.")
    return entries


def _host_list(value):
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError("hosts must be a list.")
    result = [nvmeof.nqn(item, "host_nqn", wildcard=True) for item in value]
    if len(set(result)) != len(result):
        raise ConfigurationError("hosts must not contain duplicates.")
    if "*" in result and len(result) != 1:
        raise ConfigurationError("A wildcard namespace host cannot be combined with other hosts.")
    return sorted(result)


def _namespace_desired(
    name,
    subsystem_nqn,
    rbd_image_name,
    rbd_pool,
    rbd_data_pool,
    uuid,
    rbd_image_size,
    block_size,
    load_balancing_group,
    pinned,
    trash_image,
    auto_visible,
    disable_auto_resize,
    read_only,
    location,
    rados_namespace,
    encryption_format,
    key_id,
    hosts,
    qos,
):
    nsid = int(nvmeof.namespace_id(name))
    block_size = nvmeof.integer(block_size, "block_size", minimum=1)
    if block_size not in (512, 4096):
        raise ConfigurationError("block_size must be 512 or 4096 bytes.")
    desired = {
        "nsid": nsid,
        "ns_subsystem_nqn": nvmeof.nqn(subsystem_nqn, "subsystem_nqn"),
        "rbd_image_name": nvmeof.identifier(rbd_image_name, "rbd_image_name"),
        "rbd_pool_name": nvmeof.identifier(rbd_pool, "rbd_pool"),
        "rbd_data_pool_name": _optional_identifier(rbd_data_pool, "rbd_data_pool"),
        "rados_namespace_name": _optional_identifier(rados_namespace, "rados_namespace"),
        "block_size": block_size,
        "trash_image": _boolean(trash_image, "trash_image"),
        "auto_visible": _boolean(auto_visible, "auto_visible"),
        "disable_auto_resize": _boolean(disable_auto_resize, "disable_auto_resize"),
        "read_only": _boolean(read_only, "read_only"),
        "location": _optional_text(location, "location", empty_as_none=True),
        "encryption_entries": _encryption_entries(encryption_format, key_id),
    }
    if uuid is not None:
        desired["uuid"] = nvmeof.uuid_value(uuid)
    if rbd_image_size is not None:
        desired["rbd_image_size"] = _optional_integer(
            rbd_image_size,
            "rbd_image_size",
            minimum=1,
            maximum=(1 << 63) - 1,
        )
    if load_balancing_group is not None:
        desired["load_balancing_group"] = nvmeof.integer(
            load_balancing_group,
            "load_balancing_group",
            minimum=1,
        )
        if pinned is False:
            raise ConfigurationError("pinned=False cannot be combined with load_balancing_group.")
        desired["pinned"] = True
    elif pinned is not None:
        desired["pinned"] = _boolean(pinned, "pinned")
        if pinned:
            raise ConfigurationError("pinned=True requires load_balancing_group.")
    normalized_hosts = _host_list(hosts)
    if normalized_hosts is not None:
        desired["hosts"] = normalized_hosts
    for key, value in qos.items():
        if value is not None:
            desired[key] = _optional_integer(
                value,
                key,
                maximum=(1 << 63) - 1,
            )
    return desired


def _namespace_encryption_view(value):
    if not isinstance(value, list):
        raise ProtocolError("Ceph NVMe-oF namespace returned invalid encryption entries.")
    entries = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ProtocolError("Ceph NVMe-oF namespace returned invalid encryption entries.")
        fmt = entry.get("format")
        key_id = entry.get("key_id")
        if not isinstance(fmt, str) or fmt.upper() not in ("LUKS1", "LUKS2"):
            raise ProtocolError("Ceph NVMe-oF namespace returned invalid encryption entries.")
        try:
            key_id = nvmeof.identifier(key_id, "key_id")
        except ConfigurationError as exc:
            raise ProtocolError(
                "Ceph NVMe-oF namespace returned invalid encryption entries."
            ) from exc
        entries.append({"format": fmt.upper(), "key_id": key_id})
    if len({(item["format"], item["key_id"]) for item in entries}) != len(entries):
        raise ProtocolError("Ceph NVMe-oF namespace returned duplicate encryption entries.")
    return entries


def _namespace_projection(item, desired):
    if item is None:
        return None
    result = {}
    for key in desired:
        if key == "nsid":
            try:
                result[key] = int(nvmeof.namespace_id(item.get(key)))
            except ConfigurationError as exc:
                raise ProtocolError("Ceph NVMe-oF namespace returned invalid nsid data.") from exc
        elif key == "ns_subsystem_nqn":
            try:
                result[key] = nvmeof.nqn(item.get(key), key)
            except ConfigurationError as exc:
                raise ProtocolError("Ceph NVMe-oF namespace returned invalid NQN data.") from exc
        elif key in ("rbd_image_name", "rbd_pool_name"):
            try:
                result[key] = nvmeof.identifier(item.get(key), key)
            except ConfigurationError as exc:
                raise ProtocolError(f"Ceph NVMe-oF namespace returned invalid {key} data.") from exc
        elif key in ("rbd_data_pool_name", "rados_namespace_name"):
            value = item.get(key)
            if value in (None, ""):
                result[key] = None
            else:
                try:
                    result[key] = nvmeof.identifier(value, key)
                except ConfigurationError as exc:
                    raise ProtocolError(
                        f"Ceph NVMe-oF namespace returned invalid {key} data."
                    ) from exc
        elif key == "uuid":
            try:
                result[key] = nvmeof.uuid_value(item.get(key))
            except ConfigurationError as exc:
                raise ProtocolError("Ceph NVMe-oF namespace returned invalid UUID data.") from exc
        elif key in ("block_size", "rbd_image_size", "load_balancing_group"):
            result[key] = _integer_field(item, key, key, minimum=1, maximum=(1 << 63) - 1)
        elif key in _QOS_FIELDS:
            result[key] = _integer_field(item, key, key, maximum=(1 << 63) - 1)
        elif key in (
            "trash_image",
            "auto_visible",
            "disable_auto_resize",
            "read_only",
            "pinned",
        ):
            result[key] = _boolean_field(item, key, key)
        elif key == "location":
            result[key] = _string_field(
                item,
                key,
                key,
                optional=True,
                empty_as_none=True,
            )
        elif key == "hosts":
            if not isinstance(item.get(key), list):
                raise ProtocolError("Ceph NVMe-oF namespace returned invalid hosts data.")
            try:
                result[key] = _host_list(item.get(key))
            except ConfigurationError as exc:
                raise ProtocolError("Ceph NVMe-oF namespace returned invalid hosts data.") from exc
        elif key == "encryption_entries":
            result[key] = _namespace_encryption_view(item.get(key))
    return result


def _namespace(nqn, nsid, route, profile):
    try:
        item = reconcile.data(
            __salt__["ceph_nvmeof.namespace_get"](
                nqn,
                nsid,
                profile=profile,
                **route,
            ),
            "Ceph NVMe-oF namespace read",
            expected=Mapping,
        )
    except CommandExecutionError as exc:
        if _not_found(exc):
            return None
        raise
    try:
        returned_nsid = int(nvmeof.namespace_id(item.get("nsid")))
        returned_nqn = nvmeof.nqn(item.get("ns_subsystem_nqn"), "ns_subsystem_nqn")
    except ConfigurationError as exc:
        raise ProtocolError("Ceph NVMe-oF namespace returned invalid identity data.") from exc
    if returned_nsid != nsid or returned_nqn != nqn:
        raise ProtocolError("Ceph NVMe-oF namespace response did not match the request.")
    return dict(item)


def _namespace_delete_view(item):
    result = {
        "nsid": int(nvmeof.namespace_id(item.get("nsid"))),
        "ns_subsystem_nqn": item.get("ns_subsystem_nqn"),
        "rbd_pool_name": item.get("rbd_pool_name"),
        "rbd_image_name": item.get("rbd_image_name"),
    }
    if item.get("uuid") is not None:
        result["uuid"] = item["uuid"]
    return result


def _namespace_create(
    desired,
    create_image,
    force_create,
    route,
    profile,
    timeout,
    interval,
):
    entries = desired["encryption_entries"]
    response = __salt__["ceph_nvmeof.namespace_create"](
        desired["ns_subsystem_nqn"],
        desired["rbd_image_name"],
        desired["rbd_pool_name"],
        rbd_data_pool=desired["rbd_data_pool_name"],
        nsid=desired["nsid"],
        uuid=desired.get("uuid"),
        create_image=create_image,
        rbd_image_size=desired.get("rbd_image_size"),
        trash_image=desired["trash_image"],
        block_size=desired["block_size"],
        load_balancing_group=desired.get("load_balancing_group"),
        force=force_create,
        no_auto_visible=not desired["auto_visible"],
        disable_auto_resize=desired["disable_auto_resize"],
        read_only=desired["read_only"],
        location=desired["location"],
        rados_namespace=desired["rados_namespace_name"],
        encryption_format=[entry["format"] for entry in entries] or None,
        key_id=[entry["key_id"] for entry in entries] or None,
        confirm=force_create,
        profile=profile,
        **route,
    )
    _wait(response, profile, timeout, interval)


def _namespace_confirmed_updates(current, desired, force_qos, force_hosts):
    fields = {
        "rbd_image_size",
        "load_balancing_group",
        "pinned",
        "trash_image",
        "location",
        "auto_visible",
    }
    if any(key in desired and current.get(key) != desired[key] for key in fields):
        return True
    if "hosts" in desired and set(current.get("hosts", [])).difference(desired["hosts"]):
        return True
    qos_drift = any(key in desired and current.get(key) != desired[key] for key in _QOS_FIELDS)
    hosts_drift = "hosts" in desired and current.get("hosts") != desired["hosts"]
    visibility_drift = current.get("auto_visible") != desired["auto_visible"]
    return (force_qos and qos_drift) or (force_hosts and (hosts_drift or visibility_drift))


def _namespace_replacement_values(item, desired):
    """Preserve observable fields that the declaration leaves unmanaged."""
    result = dict(desired)
    if "uuid" not in result and item.get("uuid") is not None:
        result["uuid"] = _namespace_projection(item, {"uuid": None})["uuid"]
    if "rbd_image_size" not in result and item.get("rbd_image_name") == desired["rbd_image_name"]:
        result["rbd_image_size"] = _namespace_projection(item, {"rbd_image_size": None})[
            "rbd_image_size"
        ]
    for key in _QOS_FIELDS:
        if key not in result:
            result[key] = _namespace_projection(item, {key: None})[key]
    if "hosts" not in result:
        result["hosts"] = _namespace_projection(item, {"hosts": None})["hosts"]
    if "pinned" not in result and isinstance(item.get("pinned"), bool):
        result["pinned"] = item["pinned"]
        if item["pinned"]:
            result["load_balancing_group"] = _namespace_projection(
                item,
                {"load_balancing_group": None},
            )["load_balancing_group"]
    return result


def _reconcile_namespace_updates(
    nqn,
    nsid,
    current,
    desired,
    force_qos,
    force_hosts,
    route,
    profile,
    timeout,
    interval,
):
    hosts_may_change = "hosts" in desired and (
        current.get("hosts") != desired["hosts"]
        or current.get("auto_visible") != desired["auto_visible"]
    )
    if "rbd_image_size" in desired and current.get("rbd_image_size") != desired["rbd_image_size"]:
        _wait(
            __salt__["ceph_nvmeof.namespace_resize"](
                nqn,
                nsid,
                desired["rbd_image_size"],
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )
    if desired.get("pinned") is False and current.get("pinned") is not False:
        _wait(
            __salt__["ceph_nvmeof.namespace_unpin"](
                nqn,
                nsid,
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )
    elif "load_balancing_group" in desired and (
        current.get("load_balancing_group") != desired["load_balancing_group"]
        or current.get("pinned") is not True
    ):
        _wait(
            __salt__["ceph_nvmeof.namespace_change_load_balancing_group"](
                nqn,
                nsid,
                desired["load_balancing_group"],
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )
    qos = {
        key: desired[key]
        for key in _QOS_FIELDS
        if key in desired and current.get(key) != desired[key]
    }
    if qos:
        _wait(
            __salt__["ceph_nvmeof.namespace_set_qos"](
                nqn,
                nsid,
                force=force_qos,
                confirm=force_qos,
                profile=profile,
                **route,
                **qos,
            ),
            profile,
            timeout,
            interval,
        )
    if current.get("trash_image") != desired["trash_image"]:
        _wait(
            __salt__["ceph_nvmeof.namespace_set_rbd_trash_image"](
                nqn,
                nsid,
                desired["trash_image"],
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )
    if current.get("location") != desired["location"]:
        _wait(
            __salt__["ceph_nvmeof.namespace_change_location"](
                nqn,
                nsid,
                desired["location"] or "",
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )
    if current.get("auto_visible") != desired["auto_visible"]:
        _wait(
            __salt__["ceph_nvmeof.namespace_change_visibility"](
                nqn,
                nsid,
                desired["auto_visible"],
                force=force_hosts,
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )
    if current.get("disable_auto_resize") != desired["disable_auto_resize"]:
        _wait(
            __salt__["ceph_nvmeof.namespace_set_auto_resize"](
                nqn,
                nsid,
                not desired["disable_auto_resize"],
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )

    if not hosts_may_change:
        return
    refreshed = _namespace(nqn, nsid, route, profile)
    actual_hosts = _namespace_projection(refreshed, {"hosts": desired["hosts"]})["hosts"]
    for host_nqn in sorted(set(desired["hosts"]).difference(actual_hosts)):
        _wait(
            __salt__["ceph_nvmeof.namespace_add_host"](
                nqn,
                nsid,
                host_nqn,
                force=force_hosts,
                confirm=force_hosts,
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )
    for host_nqn in sorted(set(actual_hosts).difference(desired["hosts"])):
        _wait(
            __salt__["ceph_nvmeof.namespace_delete_host"](
                nqn,
                nsid,
                host_nqn,
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            timeout,
            interval,
        )


# The public state deliberately exposes every stable GET-backed namespace field.
# pylint: disable=too-many-arguments,too-many-locals
def namespace_present(
    name,
    subsystem_nqn,
    rbd_image_name,
    rbd_pool="rbd",
    rbd_data_pool=None,
    uuid=None,
    create_image=False,
    rbd_image_size=None,
    block_size=512,
    load_balancing_group=None,
    pinned=None,
    trash_image=False,
    auto_visible=True,
    disable_auto_resize=False,
    read_only=False,
    location=None,
    rados_namespace=None,
    encryption_format=None,
    key_id=None,
    hosts=None,
    rw_ios_per_second=None,
    rw_mbytes_per_second=None,
    r_mbytes_per_second=None,
    w_mbytes_per_second=None,
    force_create=False,
    force_replace=False,
    force_qos=False,
    force_hosts=False,
    confirm=False,
    confirm_replace=False,
    gw_group=None,
    server_address=None,
    routing_traddr=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a namespace has the complete declared public GET projection.

    Mutable size, placement, QoS, trash, location, visibility, auto-resize and
    host fields use their public action endpoints. Create-only drift requires
    ``confirm_replace=True``; ``force_replace`` also removes the backing image.
    """
    ret = reconcile.state_result(name)
    try:
        for label, value in {
            "create_image": create_image,
            "force_create": force_create,
            "force_replace": force_replace,
            "force_qos": force_qos,
            "force_hosts": force_hosts,
            "confirm": confirm,
            "confirm_replace": confirm_replace,
        }.items():
            _boolean(value, label)
        if create_image and rbd_image_size is None:
            raise ConfigurationError("create_image=True requires rbd_image_size.")
        route = _routing(gw_group, server_address, routing_traddr)
        qos = {
            "rw_ios_per_second": rw_ios_per_second,
            "rw_mbytes_per_second": rw_mbytes_per_second,
            "r_mbytes_per_second": r_mbytes_per_second,
            "w_mbytes_per_second": w_mbytes_per_second,
        }
        desired = _namespace_desired(
            name,
            subsystem_nqn,
            rbd_image_name,
            rbd_pool,
            rbd_data_pool,
            uuid,
            rbd_image_size,
            block_size,
            load_balancing_group,
            pinned,
            trash_image,
            auto_visible,
            disable_auto_resize,
            read_only,
            location,
            rados_namespace,
            encryption_format,
            key_id,
            hosts,
            qos,
        )
        nqn = desired["ns_subsystem_nqn"]
        nsid = desired["nsid"]
        item = _namespace(nqn, nsid, route, profile)
        current = _namespace_projection(item, desired)
        if current == desired:
            return reconcile.no_change(ret, f"NVMe-oF namespace {nqn}/{nsid} is already current.")
        immutable_drift = []
        replacement_desired = desired
        if current is not None:
            immutable_drift = sorted(
                key
                for key in _IMMUTABLE_NAMESPACE_FIELDS.intersection(desired)
                if current.get(key) != desired[key]
            )
            if immutable_drift:
                replacement_desired = _namespace_replacement_values(item, desired)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                desired,
                f"NVMe-oF namespace {nqn}/{nsid} would be reconciled.",
            )
        if current is None or immutable_drift:
            if force_create and not confirm:
                raise ConfigurationError(
                    "Forcing NVMe-oF namespace creation requires confirm=True."
                )
        if current is None:
            _namespace_create(
                desired,
                create_image,
                force_create,
                route,
                profile,
                task_timeout,
                task_interval,
            )
        elif immutable_drift:
            if not confirm_replace:
                raise ConfigurationError(
                    "Replacing an NVMe-oF namespace with create-only drift requires "
                    "confirm_replace=True."
                )
            _wait(
                __salt__["ceph_nvmeof.namespace_delete"](
                    nqn,
                    nsid,
                    force=force_replace,
                    confirm=True,
                    profile=profile,
                    **route,
                ),
                profile,
                task_timeout,
                task_interval,
            )
            if _namespace(nqn, nsid, route, profile) is not None:
                raise ProtocolError(f"NVMe-oF namespace {nqn}/{nsid} still exists after deletion.")
            _namespace_create(
                replacement_desired,
                create_image,
                force_create,
                route,
                profile,
                task_timeout,
                task_interval,
            )
            replacement_item = _namespace(nqn, nsid, route, profile)
            replacement_current = _namespace_projection(
                replacement_item,
                replacement_desired,
            )
            if replacement_current != replacement_desired:
                _reconcile_namespace_updates(
                    nqn,
                    nsid,
                    replacement_current,
                    replacement_desired,
                    False,
                    False,
                    route,
                    profile,
                    task_timeout,
                    task_interval,
                )
        else:
            if (
                _namespace_confirmed_updates(current, desired, force_qos, force_hosts)
                and not confirm
            ):
                raise ConfigurationError(
                    "Disruptive NVMe-oF namespace updates require confirm=True."
                )
            _reconcile_namespace_updates(
                nqn,
                nsid,
                current,
                desired,
                force_qos,
                force_hosts,
                route,
                profile,
                task_timeout,
                task_interval,
            )
        after = _namespace_projection(_namespace(nqn, nsid, route, profile), desired)
        if after != desired:
            raise ProtocolError(f"NVMe-oF namespace {nqn}/{nsid} did not converge after mutation.")
        return reconcile.changed(
            ret,
            current,
            after,
            f"NVMe-oF namespace {nqn}/{nsid} was reconciled.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)


def namespace_absent(
    name,
    subsystem_nqn,
    force=False,
    confirm=False,
    gw_group=None,
    server_address=None,
    routing_traddr=None,
    profile="default",
    task_timeout=300.0,
    task_interval=2.0,
):
    """Ensure a namespace is absent; live deletion requires confirmation."""
    ret = reconcile.state_result(name)
    try:
        nsid = int(nvmeof.namespace_id(name))
        subsystem_nqn = nvmeof.nqn(subsystem_nqn, "subsystem_nqn")
        _boolean(force, "force")
        _boolean(confirm, "confirm")
        route = _routing(gw_group, server_address, routing_traddr)
        item = _namespace(subsystem_nqn, nsid, route, profile)
        if item is None:
            return reconcile.no_change(
                ret,
                f"NVMe-oF namespace {subsystem_nqn}/{nsid} is already absent.",
            )
        current = _namespace_delete_view(item)
        if __opts__.get("test", False):
            return reconcile.planned(
                ret,
                current,
                None,
                f"NVMe-oF namespace {subsystem_nqn}/{nsid} would be deleted.",
            )
        if not confirm:
            raise ConfigurationError("Deleting an NVMe-oF namespace requires confirm=True.")
        _wait(
            __salt__["ceph_nvmeof.namespace_delete"](
                subsystem_nqn,
                nsid,
                force=force,
                confirm=True,
                profile=profile,
                **route,
            ),
            profile,
            task_timeout,
            task_interval,
        )
        if _namespace(subsystem_nqn, nsid, route, profile) is not None:
            raise ProtocolError(
                f"NVMe-oF namespace {subsystem_nqn}/{nsid} still exists after deletion."
            )
        return reconcile.changed(
            ret,
            current,
            None,
            f"NVMe-oF namespace {subsystem_nqn}/{nsid} was deleted.",
        )
    except _ERRORS as exc:
        return reconcile.failed(ret, exc)
