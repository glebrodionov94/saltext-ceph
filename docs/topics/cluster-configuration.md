# Cluster configuration

The `ceph_cluster_config` execution module manages Ceph's centralized monitor
configuration database through Dashboard's `/api/cluster_conf` controller.

```bash
salt-call --local ceph_cluster_config.list
salt-call --local ceph_cluster_config.get mon_allow_pool_delete
salt-call --local ceph_cluster_config.filter \
  '["osd_max_backfills","osd_recovery_sleep"]'
salt-call --local ceph_cluster_config.set debug_ms \
  '[{"section":"mon","value":"0/3"},{"section":"osd","value":"0/5"}]'
salt-call --local ceph_cluster_config.remove debug_ms mon
salt-call --local ceph_cluster_config.bulk_set \
  '{"osd_max_backfills":{"section":"osd","value":1},"osd_recovery_sleep":{"section":"osd","value":2}}'
```

`set` accepts a complete list of assignments included in that request. A `null`
or empty-string value tells Dashboard to remove that option from the named
section. Sections omitted from the list are left unchanged. `remove` performs the
same removal explicitly for one option and section.

`bulk_set` sets exactly one section value for every named option. It does not
support removals because the Ceph controller converts every bulk value to a
string. Use `set` or `remove` when a value must be cleared.

Dashboard verifies that each option exists and can be changed at runtime before
issuing monitor commands. `force_update=true` follows Dashboard behavior and is
only accepted by Ceph for otherwise non-runtime-updatable RGW configuration.
Values can be strings, booleans, integers, or finite floating-point numbers.
Sections may include monitor-database masks such as `host:storage-1` or
`osd/rack:rack-a`.

Every function returns the common `status`, `data`, and `headers` envelope.
Mutating execution functions make changes immediately. Use
`ceph_cluster_config.managed` or `ceph_cluster_config.absent` for declarative
convergence and Salt test mode.

Current Ceph also appends cephadm manager-module options named
`mgr/cephadm/*` to the listing. Reef only returns monitor configuration options;
the client supports both response sets. The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/cluster_configuration.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/cluster_configuration.py),
and the [upstream integration tests](https://github.com/ceph/ceph/blob/main/qa/tasks/mgr/dashboard/test_cluster_configuration.py).
