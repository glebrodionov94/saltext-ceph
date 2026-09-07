# Logs, monitors, summaries, and performance counters

The read-only observability modules expose the public Dashboard controllers used
by Ceph's own web interface. They require the matching Dashboard scopes but do
not change cluster configuration.

```console
salt-call --local ceph_logs.all
salt-call --local ceph_monitor.status
salt-call --local ceph_summary.get
salt-call --local ceph_perf_counter.list
salt-call --local ceph_perf_counter.get mon a
salt-call --local ceph_perf_counter.get osd 0
```

`ceph_logs.all` returns only Dashboard's bounded in-memory buffers: currently 30
cluster entries and 30 audit entries. It is useful for event correlation, not as
a replacement for durable log storage.

`ceph_monitor.status` returns the monitor map and the `in_quorum` and
`out_quorum` groups calculated by Dashboard. `ceph_summary.get` includes health,
active and recent tasks, the active manager, and RBD mirroring counts when the
API identity has permission to read them.

`ceph_perf_counter.get` accepts the controller types `mds`, `mgr`, `mon`, `osd`,
`rbd-mirror`, `rgw`, and `tcmu-runner`. Counter sets can be large and change
between Ceph releases, so they are returned as observed data rather than modeled
as Salt states.

The routes and media version are unchanged between Reef 18.2.8 and current Ceph:
[logs](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/logs.py),
[monitor](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/monitor.py),
[performance counters](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/perf_counters.py),
and [summary](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/summary.py).
