"""Manage RBD mirroring from the salt-ssh controller."""

import functools as _functools
import inspect as _inspect

from saltext.ceph.modules import ceph_rbd_mirroring as _execution
from saltext.ceph.utils.ceph import rbd_mirroring_api as _api
from saltext.ceph.utils.ceph import salt as _salt_adapter

__virtualname__ = "ceph_rbd_mirroring"


def __virtual__():
    return __virtualname__


def _bound_values(template, args, kwargs):
    bound = _inspect.signature(template).bind(*args, **kwargs)
    bound.apply_defaults()
    profile = bound.arguments.pop("profile")
    return list(bound.arguments.values()), profile


def _operation(public_name, operation):
    template = getattr(_execution, public_name)

    @_functools.wraps(template)
    def wrapper(*args, **kwargs):
        values, profile = _bound_values(template, args, kwargs)
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
        values, profile = _bound_values(template, args, kwargs)
        return _salt_adapter.invoke(function, __opts__, {}, __context__, *values, profile=profile)

    wrapper.__module__ = __name__
    return wrapper


for _operation_name in _api.OPERATIONS:
    globals()[_operation_name] = _operation(_operation_name, _operation_name)

create_bootstrap_token = _special("create_bootstrap_token", _api.create_bootstrap_token)
import_bootstrap_token = _special("import_bootstrap_token", _api.import_bootstrap_token)
create_peer = _special("create_peer", _api.create_peer)
update_peer = _special("update_peer", _api.update_peer)

del _operation_name
