# Asynchronous tasks

Many Dashboard mutations return HTTP `202` before cephadm or a manager service
has converged. The `ceph_task` module exposes `/api/task` and a bounded waiter:

```bash
salt-call --local ceph_task.list
salt-call --local ceph_task.list name=service/create
salt-call --local ceph_task.wait service/create \
  metadata='{"service_name":"rgw.site"}' timeout=600
```

`wait` matches the task name and the supplied metadata fields, gives executing
tasks priority over older finished entries, and polls at a configurable interval.
It raises a sanitized Salt execution error on timeout or unsuccessful completion;
`fail_on_error=false` returns failed task metadata for monitoring code.

Task payloads are safe for normal Salt output and job caches by default.
Credential-shaped metadata fields are recursively masked, while `exception` and
`ret_value` are omitted because controllers may copy secrets into them. Set the
exact boolean `include_secrets=true` only for an attended diagnostic call; its
response must be handled as sensitive data and kept out of automation logs.

Dashboard tasks do not have a stable public task identifier. Avoid submitting
two concurrent mutations with the same task name and metadata. The GitOps runner
serializes reconciliation for this reason, and states always perform a final
resource read after task completion.

The implementation follows the identical [current](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/task.py)
and [Reef](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/task.py)
task controllers.
