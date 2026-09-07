"""Manage current Ceph NVMe-oF gateways from the salt-ssh controller."""

import functools as _functools
import inspect as _inspect

from saltext.ceph.modules import ceph_nvmeof as _execution
from saltext.ceph.utils.ceph import nvmeof_api as _api
from saltext.ceph.utils.ceph import salt as _salt_adapter

__virtualname__ = "ceph_nvmeof"


def __virtual__():
    return __virtualname__


def _operation(public_name):
    template = getattr(_execution, public_name)
    signature = _inspect.signature(template)

    @_functools.wraps(template)
    def wrapper(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        profile = bound.arguments.pop("profile")
        if public_name in _api.SECRET_OPERATIONS:
            return _salt_adapter.invoke(
                _api.SECRET_OPERATIONS[public_name],
                __opts__,
                {},
                __context__,
                *bound.args,
                profile=profile,
                **bound.kwargs,
            )
        return _salt_adapter.invoke(
            _api.call,
            __opts__,
            {},
            __context__,
            public_name,
            *bound.args,
            profile=profile,
            **bound.kwargs,
        )

    wrapper.__module__ = __name__
    wrapper.__signature__ = signature
    return wrapper


for _operation_name in _api.PUBLIC_OPERATIONS:
    globals()[_operation_name] = _operation(_operation_name)
