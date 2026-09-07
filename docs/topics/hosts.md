# Cephadm hosts

The `ceph_host` execution module manages hosts known to the cephadm orchestrator
through Dashboard's public `/api/host` controller.

```bash
salt-call --local ceph_host.list sources='["orchestrator"]'
salt-call --local ceph_host.get node1
salt-call --local ceph_host.create node1 address=10.0.0.11 \
  labels='["storage","_admin"]'
salt-call --local ceph_host.set_labels node1 labels='["storage"]'
salt-call --local ceph_host.toggle_maintenance node1
salt-call --local ceph_host.drain node1
salt-call --local ceph_host.delete node1 confirm=true
```

The list operation requests all hosts by default (`limit=-1`) and preserves the
Dashboard `X-Total-Count` response header. It can filter Ceph and orchestrator
sources, retrieve hardware facts, search, sort, and omit per-host service counts.

Dashboard models maintenance as a toggle. The execution function is therefore
named `toggle_maintenance` rather than implying desired-state behavior. The host
state layer reads the current status first and calls the toggle only when the
declared value differs. `drain` remains an explicit action because it schedules
daemon removal and is not a stable host property.

Diagnostic operations expose `devices`, `smart`, `inventory`, and `daemons`.
`identify_device` blinks a device LED for 1 through 3600 seconds and should be
invoked interactively.

Host deletion removes the host from cephadm orchestration and requires the real
boolean `confirm=true`.

Host list/get use API versions `1.3` and `1.2`; create, label, maintenance, and
drain use experimental `0.1`; other operations use `1.0`. These contracts are
shared by Ceph Reef and current Ceph.

The implementation follows the [current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/host.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/host.py),
and [Ceph host management documentation](https://docs.ceph.com/en/latest/cephadm/host-management/).
