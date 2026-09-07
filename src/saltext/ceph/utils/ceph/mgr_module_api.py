"""Salt-facing composition for manager module operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import mgr_module


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, profile="default"):
    """Return manager modules."""
    return mgr_module.list_(_client(opts, pillar, context, profile)).as_dict()


def get_config(opts, pillar, context, module_name, profile="default"):
    """Return persistent manager module configuration."""
    return mgr_module.get_config(_client(opts, pillar, context, profile), module_name).as_dict()


def options(opts, pillar, context, module_name, profile="default"):
    """Return manager module option definitions."""
    return mgr_module.options(_client(opts, pillar, context, profile), module_name).as_dict()


def set_config(opts, pillar, context, module_name, config, profile="default"):
    """Set supplied manager module options."""
    return mgr_module.set_config(
        _client(opts, pillar, context, profile), module_name, config
    ).as_dict()


def enable(opts, pillar, context, module_name, force=False, profile="default"):
    """Enable a manager module."""
    return mgr_module.enable(_client(opts, pillar, context, profile), module_name, force).as_dict()


def disable(opts, pillar, context, module_name, profile="default"):
    """Disable a manager module."""
    return mgr_module.disable(_client(opts, pillar, context, profile), module_name).as_dict()
