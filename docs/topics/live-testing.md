# Live cluster testing

The live suite is an explicit acceptance layer for a disposable Ceph cluster.
Ordinary unit, integration, Nox, and CI runs never enable it. The suite exercises
the shared client, typed controller adapters, real Salt execution-module loading,
state test mode, and selected reversible state lifecycles.

One machine with network access to Dashboard is sufficient. Install the
extension and run the suite there or on a dedicated control minion. The Ceph
hosts do not need Salt minions because cephadm performs host and daemon work.
A Salt master is needed only for end-to-end runner and event-bus testing.

## Safety tiers

The command-line gates are cumulative:

| Tier | Required options | Permitted work |
| --- | --- | --- |
| Read-only | `--ceph-live` | Health, inventory, typed GET calls, Salt loader checks |
| Metadata mutation | `--ceph-live --ceph-live-mutate` | UUID-named roles and users created by that test, including exact cleanup |
| Destructive | all options above plus `--ceph-live-destructive` | Reserved; writes fail closed until an endpoint-specific route rule and test are added |

Metadata mutation also requires `CEPH_TEST_EXPECTED_FSID`. The HTTP client checks
that value before its first write. Destructive tests additionally require
`CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID` to equal it byte for byte and every affected
identifier to appear in `CEPH_TEST_DESTRUCTIVE_ALLOWLIST`. Wildcards are rejected.
The current transport guard still rejects every destructive HTTP write after
those checks. Enabling a destructive scenario requires code review of a narrow
method, route, request-body, and ownership rule in the harness.

Deleting a uniquely named resource created by the current test is part of its
metadata lifecycle. Removing a host, OSD, pool, filesystem, service specification,
or any pre-existing object belongs to the destructive tier.

## Configuration

Export configuration from the test runner or secret manager. Prefer the `_FILE`
forms for credentials so values never appear in shell history or process
arguments. The example file at `tests/integration/live.env.example` is a list of
variables for humans; the test harness never loads it automatically.

```console
export CEPH_TEST_URL=https://ceph-test.example:8443
export CEPH_TEST_USERNAME_FILE=/run/secrets/ceph-dashboard-username
export CEPH_TEST_PASSWORD_FILE=/run/secrets/ceph-dashboard-password
export CEPH_TEST_VERIFY=/etc/ssl/certs/ceph-dashboard-test-ca.pem
export CEPH_TEST_EXPECTED_FSID=11111111-2222-4333-8444-555555555555
```

`CEPH_TEST_VERIFY=false` is available for a disposable cluster with a self-signed
certificate. Production-like testing should supply the CA file. Optional
controllers and release-specific routes are enabled explicitly, for example:

```console
export CEPH_TEST_FEATURES=orchestrator,health_snapshot,hardware
```

This distinguishes a missing backend from an incompatible API. RGW, NFS, SMB,
NVMe-oF, iSCSI, Prometheus, and Grafana failures must not be hidden by a broad
catch-and-skip rule when their feature is declared. Use `cephfs` and `rbd` when
those storage backends are expected. `health_snapshot` and `hardware` enable
current-only Dashboard routes which Reef does not provide.

## Commands

Run the read-only suite through its isolated Nox session:

```console
nox -s live
```

The session restricts paths to `tests/integration`, accepts only a small set of
safe pytest selection and reporting options, keeps capture enabled, and masks
ambient pytest controls because fixture locals can contain credentials. Run a
metadata lifecycle only on the disposable cluster:

```console
nox -s live -- --ceph-live-mutate tests/integration/states
```

The equivalent direct pytest command must include both gates:

```console
python -m pytest tests/integration/states -q \
  --ceph-live --ceph-live-mutate
```

Every mutable test reserves an unpredictable `saltext-ci-*` identifier, proves
it did not exist, and removes only that exact object in `finally`. The lifecycle
checks create, idempotent re-apply, planned update, live update, planned deletion,
refusal without `confirm=True`, confirmed deletion, and final absence.

OSD provisioning is intentionally separate. Use stable `/dev/disk/by-id/...`
identifiers, verify Dashboard reports each disk available, and allowlist every
host and disk. Do not use `all: true` in an acceptance job. OSDs can remain part
of the durable test-cluster fixture instead of being destroyed after every run.

## Recorded compatibility

On 2026-09-07, the read-only suite passed against Ceph 20.2.4 Tentacle through a
self-signed Dashboard endpoint. It covered authentication, health, FSID, summary,
monitor data, current hardware data, cephadm host/service/daemon inventory,
storage defaults, CRUSH and erasure profiles, and real Salt execution-module
loading. The cluster had one orchestrator host and no OSDs, so OSD-dependent and
unavailable optional RBD checks were correctly skipped. Live state acceptance
covers reversible Dashboard metadata; storage-service tests remain behind the
destructive gate.
