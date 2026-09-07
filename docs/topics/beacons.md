# Ceph event beacons

The extension provides three read-only Salt beacons for event-driven operations.
Each beacon performs one Dashboard resource read per scheduled run, keeps only
bounded transition state in the minion's in-memory `__context__`, and never
changes the cluster. Salt adds the returned `tag` suffix to
`salt/beacon/<minion-id>/<configured-name>/`.

Beacons run on every minion loop by default. Always configure an `interval`
appropriate for the API and the reaction time you need. The interval is enforced
by Salt before the Python beacon is called.

## Cluster health

`ceph_health` reads the compact `/api/health/minimal` representation. It emits:

- `degraded` when the status first differs from `HEALTH_OK`, or when the status
  or health-check fingerprint changes while degraded;
- `recovered` when a previously degraded cluster returns to `HEALTH_OK`;
- `unreachable` on the first consecutive API or response-validation failure;
- `reachable` on the first successful read after an unreachable event.

The first healthy observation establishes the baseline without an event. A
degraded first observation is reported immediately. Health events contain the
status, SHA-256 fingerprint, total check count, and a bounded summary of checks.
Repeated identical observations are suppressed.

```yaml
beacons:
  ceph_cluster_health:
    - beacon_module: ceph_health
    - profile: default
    - interval: 30
    - max_checks: 20
```

`max_checks` controls how many check summaries appear in an event and accepts
values from 1 through 100. The fingerprint still covers every parsed check, up
to the internal safety limit of 1024 checks.

## Completed tasks

`ceph_task` reads `/api/task` once and identifies new entries in
`finished_tasks`. Its first run records a baseline, so historical completions do
not trigger reactors. `emit_existing: true` opts into emitting the initial
result. Failed tasks produce `failed`; successful tasks produce `succeeded` only
when `failures_only` is false.

```yaml
beacons:
  ceph_failed_tasks:
    - beacon_module: ceph_task
    - profile: default
    - interval: 10
    - failures_only: true
    - emit_existing: false
    - cache_size: 256
    # name: service/create
```

`cache_size` accepts 1 through 256 and also bounds the number of finished tasks
processed per run. Task events include a derived identifier, name, success,
timestamps, duration, and progress when present. Raw Dashboard task `metadata`,
`ret_value`, and `exception` fields are neither emitted nor retained. This keeps
credentials or service specifications that may occur in task bodies off the Salt
event bus. Metadata used to distinguish completions is hashed with a 64 KiB
canonical-input limit; malformed or oversized task records are skipped.

## Certificate expiry

`ceph_certificate` makes one certificate-list request and emits severity changes
for each certificate identity (`cert_name`, `scope`, and `target`):

- `warning` at or below `warning_days`;
- `critical` at or below `critical_days`, and for invalid or unconfigured
  certificate records;
- `expired` after the expiry instant or when Ceph reports `expired`;
- `recovered` when a previously unhealthy certificate becomes healthy.

```yaml
beacons:
  ceph_certificate_expiry:
    - beacon_module: ceph_certificate
    - profile: default
    - interval: 3600
    - warning_days: 30
    - critical_days: 7
    - include_cephadm_signed: true
    # scope: service
    # service_type: rgw*
```

`critical_days` cannot exceed `warning_days`; both accept 0 through 3650. The
beacon recalculates whole remaining days from `expiry_date` against UTC on every
run, with `days_to_expiration` as a fallback for API variants without a usable
timestamp. Events contain only the certificate name, scope, target, status,
expiry date, and remaining days. PEM, private-key, subject, issuer, extension,
and detailed certificate fields are discarded. The Dashboard certificate
controller is available in current Ceph and is absent in Reef. An unknown or
malformed certificate status is treated as `critical`, so a new API status cannot
silently suppress monitoring.

## Operational behavior

Connection settings come from the named `ceph:profiles` profile used by the
execution modules. API errors in the task and certificate beacons are logged by
exception type without an event body; the health beacon turns them into the
edge-triggered reachability events described above. Restarting or refreshing the
minion clears transition caches and establishes a new baseline. Non-successful or
malformed Salt response envelopes are treated as read failures. Each beacon keeps
at most 32 independent configuration instances in memory; health parsing is
capped at 1,024 checks and certificate parsing at 512 entries.

Use distinct top-level names plus `beacon_module` for multiple profiles or
filters. Salt passes that configured name to the beacon, so their caches remain
isolated. Reactors should remain idempotent and should treat beacon data as an
observation that can become stale after it is emitted.

The implementation follows Salt's [beacon plugin contract](https://docs.saltproject.io/en/latest/topics/beacons/index.html),
the Ceph [health controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/health.py),
[task controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/task.py),
and [certificate model](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/model/certificate.py).
