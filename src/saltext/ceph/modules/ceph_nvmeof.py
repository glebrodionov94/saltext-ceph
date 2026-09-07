"""Manage current Ceph NVMe-oF gateways through the Dashboard REST API."""

import functools as _functools
import inspect as _inspect

from saltext.ceph.utils.ceph import nvmeof_api as _api
from saltext.ceph.utils.ceph import salt as _salt_adapter

__virtualname__ = "ceph_nvmeof"


def __virtual__():
    return __virtualname__


def _call(operation, *args, profile="default", **kwargs):
    return _salt_adapter.invoke(
        _api.call,
        __opts__,
        __pillar__,
        __context__,
        operation,
        *args,
        profile=profile,
        **kwargs,
    )


def _normal_operation(operation, template):
    parameters = list(_inspect.signature(template).parameters.values())[1:]
    parameters.append(
        _inspect.Parameter(
            "profile",
            _inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default="default",
        )
    )
    signature = _inspect.Signature(parameters)

    def function(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        profile = bound.arguments.pop("profile")
        return _call(operation, *bound.args, profile=profile, **bound.kwargs)

    _functools.update_wrapper(function, template)
    function.__name__ = operation
    function.__qualname__ = operation
    function.__module__ = __name__
    function.__signature__ = signature
    function.__doc__ = (
        f"{template.__doc__}\n\n"
        "CLI Example:\n\n"
        ".. code-block:: bash\n\n"
        f"    salt-call --local ceph_nvmeof.{operation} ..."
    )
    return function


def _secret_operation(operation, template):
    parameters = list(_inspect.signature(template).parameters.values())[3:]
    signature = _inspect.Signature(parameters)

    def function(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        return _salt_adapter.invoke(
            template,
            __opts__,
            __pillar__,
            __context__,
            *bound.args,
            **bound.kwargs,
        )

    _functools.update_wrapper(function, template)
    function.__name__ = operation
    function.__qualname__ = operation
    function.__module__ = __name__
    function.__signature__ = signature
    function.__doc__ = (
        f"{template.__doc__}\n\n"
        "Secret arguments are absolute source-file paths.\n\n"
        "CLI Example:\n\n"
        ".. code-block:: bash\n\n"
        f"    salt-call --local ceph_nvmeof.{operation} ..."
    )
    return function


for _operation_name, _template in _api.OPERATIONS.items():
    globals()[_operation_name] = _normal_operation(_operation_name, _template)

for _operation_name, _template in _api.SECRET_OPERATIONS.items():
    globals()[_operation_name] = _secret_operation(_operation_name, _template)

del _operation_name
del _template
