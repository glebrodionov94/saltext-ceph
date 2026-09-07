"""Manage CephFS from the salt-ssh controller through Dashboard REST API."""

import functools as _functools
import inspect as _inspect

from saltext.ceph.modules import cephfs as _execution
from saltext.ceph.utils.ceph import cephfs_api as _api
from saltext.ceph.utils.ceph import salt as _salt_adapter

__virtualname__ = "cephfs"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _bind(function, args, kwargs):
    signature = _inspect.signature(function)
    bound = signature.bind(*args, **kwargs)
    bound.apply_defaults()
    profile = bound.arguments.pop("profile")
    return list(bound.arguments.values()), profile


def _operation(public_name, operation):
    template = getattr(_execution, public_name)

    @_functools.wraps(template)
    def wrapper(*args, **kwargs):
        values, profile = _bind(template, args, kwargs)
        return _salt_adapter.invoke(
            _api.call,
            __opts__,
            {},
            __context__,
            operation,
            *values,
            profile=profile,
        )

    wrapper.__module__ = __name__
    return wrapper


def _special(public_name, function):
    template = getattr(_execution, public_name)

    @_functools.wraps(template)
    def wrapper(*args, **kwargs):
        values, profile = _bind(template, args, kwargs)
        return _salt_adapter.invoke(function, __opts__, {}, __context__, *values, profile=profile)

    wrapper.__module__ = __name__
    return wrapper


for _operation_name in _api.OPERATIONS:
    _public_name = _operation_name
    if _public_name == "list":
        _public_name = "list_"
    globals()[_public_name] = _operation(_public_name, _operation_name)

write_file = _special("write_file", _api.write_file)
mirror_create_token = _special("mirror_create_token", _api.mirror_create_token)
mirror_add_peer = _special("mirror_add_peer", _api.mirror_add_peer)

del _public_name
del _operation_name
