"""Inspect cluster status and control cephadm upgrades through Dashboard API."""

from saltext.ceph.utils.ceph import cluster_api
from saltext.ceph.utils.ceph import salt as salt_adapter

__virtualname__ = "ceph_cluster"


def __virtual__():
    return __virtualname__


def status(profile="default"):
    """Return the cluster installation status marker.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster.status

    """
    return salt_adapter.invoke(cluster_api.status, __opts__, __pillar__, __context__, profile)


def set_status(cluster_status, profile="default"):
    """Set ``INSTALLED`` or ``POST_INSTALLED``.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster.set_status POST_INSTALLED
    """
    return salt_adapter.invoke(
        cluster_api.set_status, __opts__, __pillar__, __context__, cluster_status, profile
    )


def upgrade_list(tags=False, image=None, show_all_versions=False, profile="default"):
    """List available cephadm upgrade targets.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster.upgrade_list

    """
    return salt_adapter.invoke(
        cluster_api.upgrade_list,
        __opts__,
        __pillar__,
        __context__,
        tags,
        image,
        show_all_versions,
        profile,
    )


def upgrade_status(profile="default"):
    """Return current cephadm upgrade progress.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster.upgrade_status

    """
    return salt_adapter.invoke(
        cluster_api.upgrade_status, __opts__, __pillar__, __context__, profile
    )


def upgrade_start(
    image=None,
    version=None,
    daemon_types=None,
    host_placement=None,
    services=None,
    limit=None,
    profile="default",
):
    """Start a cephadm upgrade, optionally limited to a deployment subset.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster.upgrade_start version=18.2.7
    """
    return salt_adapter.invoke(
        cluster_api.upgrade_start,
        __opts__,
        __pillar__,
        __context__,
        image,
        version,
        daemon_types,
        host_placement,
        services,
        limit,
        profile,
    )


def upgrade_pause(profile="default"):
    """Pause an active cephadm upgrade.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster.upgrade_pause

    """
    return salt_adapter.invoke(
        cluster_api.upgrade_pause, __opts__, __pillar__, __context__, profile
    )


def upgrade_resume(profile="default"):
    """Resume a paused cephadm upgrade.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster.upgrade_resume

    """
    return salt_adapter.invoke(
        cluster_api.upgrade_resume, __opts__, __pillar__, __context__, profile
    )


def upgrade_stop(profile="default"):
    """Stop an active cephadm upgrade.

    CLI Example:

    .. code-block:: bash

        salt-call --local ceph_cluster.upgrade_stop

    """
    return salt_adapter.invoke(cluster_api.upgrade_stop, __opts__, __pillar__, __context__, profile)
