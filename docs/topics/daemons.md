# Cephadm daemons

The `ceph_daemon` execution module maps Dashboard's public `/api/daemon`
controller. It lists orchestrator daemons and schedules supported lifecycle
actions.

```bash
salt-call --local ceph_daemon.list
salt-call --local ceph_daemon.list daemon_types='["mon","mgr","osd"]'
salt-call --local ceph_daemon.action osd.1 restart
salt-call --local ceph_daemon.action rgw.site.node1 stop force=true
salt-call --local ceph_daemon.action mgr.node1.abcd redeploy \
  container_image=quay.io/ceph/ceph@sha256:abc123
```

Supported actions are `start`, `stop`, `restart`, and `redeploy`. An explicit
`container_image` is valid only for `redeploy`. The orchestrator records the
action and cephadm performs it asynchronously during its serve loop.

Current Ceph can use `force=true` with `stop` and `restart` to bypass an
`ok-to-stop` refusal. The module omits `force` when false, keeping ordinary
actions compatible with Reef, whose Dashboard controller does not expose that
parameter.

Daemon listing uses API version `1.0`; actions use experimental API version
`0.1`. Every call returns the common `status`, `data`, and `headers` envelope.
The controller has no public endpoint for retrieving one daemon, so the module
does not invent a local `get` operation.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/daemon.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/daemon.py),
and the [upstream controller tests](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/tests/test_daemon.py).
