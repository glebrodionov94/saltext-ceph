"""Manage Ceph manager modules through the Dashboard REST API."""

from saltext.ceph.utils.ceph import mgr_module_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_mgr_module"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def _invoke(function, *args):
    return salt_adapter.invoke(function, __opts__, __pillar__, __context__, *args)


def list_(profile="default"):
    """Return managed manager modules.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_mgr_module.list
    """
    return _invoke(mgr_module_api.list_, profile)


def get_config(module_name, profile="default"):
    """Return persistent configuration values for a manager module.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_mgr_module.get_config prometheus
    """
    return _invoke(mgr_module_api.get_config, module_name, profile)


def options(module_name, profile="default"):
    """Return option definitions for a manager module.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_mgr_module.options prometheus
    """
    return _invoke(mgr_module_api.options, module_name, profile)


def set_config(module_name, config, profile="default"):
    """Set supplied persistent manager module options.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_mgr_module.set_config prometheus \\
          config='{"server_port":9283}'
    """
    return _invoke(mgr_module_api.set_config, module_name, config, profile)


def enable(module_name, force=False, profile="default"):
    """Enable a manager module.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_mgr_module.enable prometheus
    """
    return _invoke(mgr_module_api.enable, module_name, force, profile)


def disable(module_name, profile="default"):
    """Disable a manager module.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_mgr_module.disable prometheus
    """
    return _invoke(mgr_module_api.disable, module_name, profile)
