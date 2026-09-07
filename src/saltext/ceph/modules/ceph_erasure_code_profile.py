"""Manage erasure-code profiles through the Ceph Dashboard REST API."""

from saltext.ceph.utils.ceph import erasure_code_profile_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_erasure_code_profile"
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(profile="default"):
    """Return all erasure-code profiles.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_erasure_code_profile.list
    """
    return salt_adapter.invoke(
        erasure_code_profile_api.list_, __opts__, __pillar__, __context__, profile
    )


def get(name, profile="default"):
    """Return one erasure-code profile by name.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_erasure_code_profile.get ec42
    """
    return salt_adapter.invoke(
        erasure_code_profile_api.get, __opts__, __pillar__, __context__, name, profile
    )


def create(name, settings=None, profile="default"):
    """Create a profile from a mapping of plugin-specific settings.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_erasure_code_profile.create ec42 \\
          settings='{"plugin":"jerasure","k":4,"m":2,"crush-failure-domain":"host"}'
    """
    return salt_adapter.invoke(
        erasure_code_profile_api.create,
        __opts__,
        __pillar__,
        __context__,
        name,
        settings,
        profile,
    )


def delete(name, confirm=False, profile="default"):
    """Delete one erasure-code profile after explicit confirmation.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_erasure_code_profile.delete ec42 confirm=true
    """
    return salt_adapter.invoke(
        erasure_code_profile_api.delete,
        __opts__,
        __pillar__,
        __context__,
        name,
        confirm,
        profile,
    )
