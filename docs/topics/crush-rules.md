# CRUSH rules

The `ceph_crush_rule` execution module manages public Dashboard
`/api/crush_rule` resources.

```bash
salt-call --local ceph_crush_rule.list
salt-call --local ceph_crush_rule.get replicated_ssd
salt-call --local ceph_crush_rule.create replicated_ssd host \
  root=default device_class=ssd
salt-call --local ceph_crush_rule.create ec_ssd host \
  pool_type=erasure erasure_profile=ec42 device_class=ssd
salt-call --local ceph_crush_rule.delete replicated_ssd confirm=true
```

Replicated rules require `root` for compatibility with Ceph Reef. Their request
omits the newer `pool_type` and erasure-profile fields, so the same operation works
with Reef and current Ceph.

Current Ceph also supports `pool_type=erasure`. `erasure_profile` is sent to the
Dashboard controller as `profile`; the distinct Salt argument leaves `profile`
available for selecting the configured Dashboard connection. `root` applies only
to replicated rules, while `erasure_profile` applies only to erasure rules.

Reads use Dashboard API version `2.0`; create and delete use version `1.0`.
Deletion requires the real boolean `confirm=true`. Every
function returns the common `status`, `data`, and `headers` envelope. Mutations
are immediate execution operations. Use `ceph_crush_rule.present` and
`ceph_crush_rule.absent` for idempotent reconciliation and Salt test mode.

The internal `/ui-api/crush_rule/info` endpoint is excluded. Its node and root
data are presentation helpers rather than a CRUSH-rule resource contract.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/crush_rule.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/crush_rule.py),
and the [upstream integration tests](https://github.com/ceph/ceph/blob/main/qa/tasks/mgr/dashboard/test_crush_rule.py).
