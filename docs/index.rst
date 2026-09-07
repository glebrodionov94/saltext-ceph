``saltext-ceph``: Integrate Salt with Ceph
==========================================

Salt Extension for interacting with Ceph through the Dashboard REST API

This project provides typed execution modules and salt-ssh wrappers for the
public Ceph Dashboard API, declarative state modules for readable resources,
GitOps runners, and read-only event beacons. Cephadm remains the cluster
orchestrator while Salt calculates and verifies desired state.

.. toctree::
  :maxdepth: 2
  :caption: Guides
  :hidden:

  topics/installation
  topics/api-client
  topics/support
  topics/controller-coverage
  topics/permissions
  topics/gitops
  topics/ceph-users
  topics/cephfs
  topics/rbd
  topics/rbd-groups
  topics/rbd-mirroring
  topics/nfs
  topics/iscsi
  topics/smb
  topics/rgw-daemon
  topics/rgw-user
  topics/rgw-bucket
  topics/rgw-topic
  topics/rgw-multisite
  topics/rgw-iam
  topics/rgw-states
  topics/nvmeof
  topics/certificates
  topics/cluster
  topics/cluster-configuration
  topics/crush-rules
  topics/daemons
  topics/dashboard-roles
  topics/dashboard-settings
  topics/dashboard-users
  topics/erasure-code-profiles
  topics/feature-toggles
  topics/grafana
  topics/hardware
  topics/health
  topics/hosts
  topics/manager-modules
  topics/multi-cluster
  topics/motd
  topics/osds
  topics/observability
  topics/pools
  topics/prometheus
  topics/runners
  topics/services
  topics/tasks
  topics/telemetry
  topics/beacons
  topics/development
  topics/releasing

.. toctree::
  :maxdepth: 2
  :caption: Provided Modules
  :hidden:

  ref/modules/index
  ref/states/index
  ref/wrapper/index
  ref/runners/index
  ref/beacons/index
  ref/utils/index

.. toctree::
  :maxdepth: 2
  :caption: Reference
  :hidden:

  changelog


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
