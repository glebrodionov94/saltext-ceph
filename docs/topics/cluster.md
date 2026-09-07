# Cluster status and cephadm upgrades

The `ceph_cluster` execution module maps Dashboard's `/api/cluster` and
`/api/cluster/upgrade` controllers. It exposes the Dashboard installation marker
and cephadm's native rolling-upgrade controls.

```bash
salt-call --local ceph_cluster.status
salt-call --local ceph_cluster.set_status POST_INSTALLED
salt-call --local ceph_cluster.upgrade_list
salt-call --local ceph_cluster.upgrade_list tags=true \
  image=quay.io/ceph/ceph show_all_versions=true
salt-call --local ceph_cluster.upgrade_status
salt-call --local ceph_cluster.upgrade_start version=18.2.7
salt-call --local ceph_cluster.upgrade_start \
  image=registry.example/ceph/ceph@sha256:abc123 \
  daemon_types='["mgr","mon"]' host_placement='host1 host2' limit=2
salt-call --local ceph_cluster.upgrade_pause
salt-call --local ceph_cluster.upgrade_resume
salt-call --local ceph_cluster.upgrade_stop
```

`upgrade_start` requires exactly one of `version` or `image`. `daemon_types` and
`services` are mutually exclusive non-empty lists. `host_placement` retains the
cephadm placement string, and `limit` is a positive integer. Ceph performs the
cluster-aware safety checks, upgrade-order validation, image inspection, and
orchestration.

Mutations return the common `status`, `data`, and `headers` envelope. A `202`
response means Dashboard accepted an asynchronous task; the HTTP client does not
poll it. Use `upgrade_status` to observe the cephadm operation. These execution
functions issue commands directly. Upgrade start, pause, resume, and stop remain
imperative because repeatedly enforcing those transitions during highstate would
be unsafe.

The cluster status endpoints use Dashboard's experimental API version `0.1` and
only accept `INSTALLED` or `POST_INSTALLED`. Upgrade endpoints use API version
`1.0`. The implementation follows both the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/cluster.py)
and the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/cluster.py),
which expose the same operations. Dashboard's
[upgrade controller tests](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/tests/test_cluster_upgrade.py)
also retain an older list response, so the client accepts both that list and the
newer object returned by cephadm.
