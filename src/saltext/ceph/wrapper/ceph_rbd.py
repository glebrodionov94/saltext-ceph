"""Manage RBD images from the salt-ssh controller."""

import functools as _functools
import inspect as _inspect

from saltext.ceph.modules import ceph_rbd as _execution
from saltext.ceph.utils.ceph import rbd_api as _api
from saltext.ceph.utils.ceph import salt as _salt_adapter

__virtualname__ = "ceph_rbd"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _operation(public_name, operation):
    template = getattr(_execution, public_name)

    @_functools.wraps(template)
    def wrapper(*args, **kwargs):
        bound = _inspect.signature(template).bind(*args, **kwargs)
        bound.apply_defaults()
        profile = bound.arguments.pop("profile")
        return _salt_adapter.invoke(
            _api.call,
            __opts__,
            {},
            __context__,
            operation,
            *bound.arguments.values(),
            profile=profile,
        )

    wrapper.__module__ = __name__
    return wrapper


for _operation_name in _api.OPERATIONS:
    _public_name = "list_" if _operation_name == "list" else _operation_name
    globals()[_public_name] = _operation(_public_name, _operation_name)

del _public_name
del _operation_name
