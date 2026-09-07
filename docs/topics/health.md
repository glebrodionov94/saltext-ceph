# Cluster health

The `ceph_health` execution module exposes the permission-filtered health views
from Ceph Dashboard.

```bash
salt-call --local ceph_health.minimal
salt-call --local ceph_health.full
salt-call --local ceph_health.capacity
salt-call --local ceph_health.fsid
salt-call --local ceph_health.telemetry_enabled
salt-call --local ceph_health.snapshot
```

`minimal` is the preferred polling input. `full` can return large OSD, filesystem,
pool, and CRUSH structures and should be called only when those details are
needed. `snapshot` is a current-release status-like view; it is not available in
Ceph Reef. The other operations work with Reef and current Ceph.

All functions are read-only, use Dashboard API version `1.0`, and return the
common `status`, `data`, and `headers` envelope. A health beacon can consume the
minimal response and emit events only when status or checks change.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/health.py)
and [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/health.py).
