# Runners and GitOps execution

`saltext.ceph` provides two master-side runner modules. They are optional: all
execution and state modules also work with `salt-call --local` on a single
management node.

## Direct API runner

The `ceph` runner resolves `ceph:profiles` from the Salt master configuration.
It exposes a small operational surface for connectivity and asynchronous task
inspection:

```console
salt-run ceph.ping profile=default
salt-run ceph.tasks name=service/create
salt-run ceph.wait_task service/create metadata='{"service_name":"rgw.site"}'
salt-run ceph.clear_cache
```

Task output recursively masks credential fields and omits `exception` and
`ret_value`. An attended diagnostic can request the original Dashboard payload
with `include_secrets=true`; do not use that option in CI because Salt job caches
may retain the response. A `wait_task` metadata filter is also recorded as a
runner argument, so use only non-secret identifiers in that filter.

Keeping an API profile on the master is optional. In the recommended topology,
credentials stay only in the control minion's encrypted pillar and the GitOps
runner invokes that minion.

## Exact-target GitOps runner

`ceph_gitops` accepts one literal minion ID and uses Salt's list target type. It
requires the intended Ceph FSID, checks `ceph_health.fsid`, refuses an overlapping
state job, and then calls `state.apply` with `queue=false`.

```console
salt-run ceph_gitops.plan ceph-control \
  11111111-1111-1111-1111-111111111111 mods='[ceph.cluster]'

salt-run ceph_gitops.apply ceph-control \
  11111111-1111-1111-1111-111111111111 mods='[ceph.cluster]'
```

`plan` sets Salt test mode; the state modules in this extension do not perform API
mutations in that mode. `apply` enables normal state execution. The state tree and
pillar should come from version-controlled Salt files or an external pillar
backend. Runner arguments deliberately do not accept credentials or inline
pillar, because master job caches and event buses can retain command arguments.

`ceph_gitops.running` reports only the active job's function, numeric job ID, and
numeric process ID when those values are valid. Salt versions that include the
original positional or keyword arguments in `saltutil.running` are filtered so
inline pillar and other argument data cannot enter the runner result.

The preflight check reduces accidental concurrent runs but is not a distributed
lock. A GitHub Actions workflow or another GitOps controller should also use one
concurrency group per Ceph cluster.
