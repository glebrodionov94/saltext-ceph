# Live cluster testing

The live suite is an explicit acceptance layer for a disposable Ceph cluster.
Ordinary unit, integration, Nox, and CI runs never enable it. The suite exercises
the shared client, typed controller adapters, real Salt execution-module loading,
state test mode, and guarded resource lifecycles.

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
| Destructive | All options above plus `--ceph-live-destructive` | Exact allowlisted host, service, OSD, RBD, CephFS, and RGW lifecycles |

Metadata mutation requires `CEPH_TEST_EXPECTED_FSID`. The HTTP client verifies
that value before its first write. Destructive tests additionally require:

- `CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID`, which must match
  `CEPH_TEST_EXPECTED_FSID` byte for byte;
- `CEPH_TEST_DESTRUCTIVE_ALLOWLIST`, a comma-separated list containing every
  exact resource identifier used by the selected test; and
- the `--ceph-live`, `--ceph-live-mutate`, and `--ceph-live-destructive`
  command-line gates in the same invocation.

Wildcards and glob characters are rejected. Passing the three gates does not
open unrestricted writes: the guarded client also checks the HTTP method, route,
API version, query, request body, active resource lease, and ownership evidence.
Any destructive request without a reviewed rule fails closed. Each lifecycle
proves that its named resources are initially absent and cleans up only resources
whose ownership it can still establish.

Deleting a uniquely named role or user created by the current test is part of
the metadata tier. Removing a host, OSD, pool, filesystem, service specification,
or storage object belongs to the destructive tier, even when the same test
created it.

## Connection and feature configuration

Export configuration from the test runner or secret manager. Prefer the `_FILE`
forms for credentials so values never appear in shell history or process
arguments. The example file at `tests/integration/live.env.example` is a list of
variables for humans; the test harness never loads it automatically. Keep real
Dashboard addresses, credentials, FSIDs, and device identities out of the
repository.

```console
export CEPH_TEST_URL=<dashboard-url>
export CEPH_TEST_USERNAME_FILE=<absolute-username-secret-file>
export CEPH_TEST_PASSWORD_FILE=<absolute-password-secret-file>
export CEPH_TEST_VERIFY=<ca-file-or-true>
export CEPH_TEST_EXPECTED_FSID=<cluster-fsid>
```

`CEPH_TEST_VERIFY=false` is available for a disposable cluster with a self-signed
certificate. Production-like testing should supply the CA file. Optional
controllers and release-specific routes are enabled explicitly, for example:

```console
export CEPH_TEST_FEATURES=orchestrator,rbd,cephfs,rgw
```

This distinguishes a missing backend from an incompatible API. RGW, NFS, SMB,
NVMe-oF, iSCSI, Prometheus, and Grafana failures must not be hidden by a broad
catch-and-skip rule when their feature is declared. `health_snapshot` and
`hardware` enable current-only Dashboard routes which Reef does not provide.

Before a destructive run, set the second FSID confirmation and construct the
allowlist from the exact identities documented below:

```console
export CEPH_TEST_DESTRUCTIVE_CONFIRM_FSID=<same-cluster-fsid>
export CEPH_TEST_DESTRUCTIVE_ALLOWLIST='<kind:id>,<kind:id>'
```

## Infrastructure lifecycles

The host lifecycle requires `orchestrator` in `CEPH_TEST_FEATURES` and these
values:

- `CEPH_TEST_INFRA_HOSTNAME` and `CEPH_TEST_INFRA_HOST_ADDRESS` identify an
  initially absent host;
- `host:<hostname>` must be in `CEPH_TEST_DESTRUCTIVE_ALLOWLIST`.

It plans creation, adds an ownership label, verifies an idempotent re-apply,
updates the labels, and checks deletion planning and confirmation. cephadm may
automatically place monitors, managers, crash collectors, or exporters on a new
host. The lifecycle therefore drains its owned host and waits for service
instances to leave before removing it.

The service lifecycle also requires `orchestrator` and uses:

- `CEPH_TEST_INFRA_SERVICE_HOST` for an existing orchestrator host;
- optional `CEPH_TEST_INFRA_SERVICE_NAME` for an initially absent, unique
  `rgw.saltext-ci-*` service (the default is `rgw.saltext-ci-live-rgw`); and
- both `service:<service-name>` and `host:<placement-host>` in the allowlist.

It creates the service as unmanaged, verifies idempotency, changes it to managed,
verifies convergence, and removes only that exact service after the confirmation
checks.

## OSD lifecycle

The OSD lifecycle requires `orchestrator`, at least three pre-existing `up` and
`in` OSDs, a host already registered with cephadm, and one empty device which
Dashboard reports as available. It has no default identities; set all three:

- `CEPH_TEST_OSD_SERVICE`, using one unique `osd.saltext-ci-*` service name;
- `CEPH_TEST_OSD_HOST`, matching the registered host; and
- `CEPH_TEST_OSD_DEVICE`, matching one exact `/dev/...` path in Dashboard
  inventory. Prefer a stable `/dev/disk/by-id/...` path when the inventory
  exposes it.

The allowlist must contain:

```text
service:<osd-service>
host:<osd-host>
device:<osd-host>:<exact-device-path>
```

If Dashboard inventory reports a device ID, also add
`device-id:<osd-host>:<device-id>`. The test submits a drive group whose
`data_devices.paths` contains only the configured path; it never uses
`all: true`. It then proves that exactly one new OSD came from that device,
reconciles the `saltext_ci` device class, marks the service unmanaged to prevent
redeployment, and exercises planned, refused, confirmed, and idempotent OSD
removal before deleting the service specification.

All pools that can place data on the disposable OSD must also tolerate the OSD
being stopped. On a three-OSD cluster, use replicated pools with `size=3` and
`min_size=2`, including internal pools such as `.mgr`. A size-one pool can make
cephadm's `ok-to-stop` check refuse the drain even when the lifecycle itself is
correct.

### Reusing a device after Ceph 20.2 OSD removal

In the Ceph Dashboard 20.2 acceptance environment, an OSD removal completed
through the Dashboard API but did not erase the ceph-volume LVM metadata. The
disk therefore remained unavailable for another OSD lifecycle. The acceptance
test deliberately does not turn an API deletion into an implicit disk wipe.

Before reusing that disk, verify the host and exact device outside the test and
explicitly zap it through cephadm, for example:

```console
ceph orch device zap <host> <exact-device-path> --force
```

An administrator can instead run the equivalent ceph-volume cleanup in the
target host's Ceph environment:

```console
ceph-volume lvm zap <exact-device-path> --destroy
```

Recheck `ceph orch device ls --refresh` and wait for the device to become
available before running the OSD lifecycle again. Also confirm that no remaining
managed drive-group specification can automatically redeploy an OSD on the
freshly zapped device. The zap is intentionally an external, separately reviewed
action because it irreversibly destroys the selected device's storage metadata.
See Ceph's [device-zap guidance](https://docs.ceph.com/en/latest/cephadm/services/osd/#erasing-devices-zapping-devices)
and [ceph-volume zap reference](https://docs.ceph.com/en/latest/ceph-volume/lvm/zap/).

## Storage lifecycles

The RBD, CephFS, and RGW lifecycles require at least three pre-existing `up` and
`in` OSDs and `mon_allow_pool_delete=true`. They mark ownership on resources
where the API supports it, exercise test mode, create, update, idempotent
re-apply, confirmed deletion, and clean up in reverse dependency order. RBD and
CephFS create dedicated three-replica pools with `min_size=2`.

Dashboard can report a pool-create task as complete before every requested
property is visible. An enabled autoscaler can also change `pg_num` during that
window. The pool state waits for the pool to appear, reads it again, submits at
most one corrective update for mutable drift, and then waits for the exact
declared view. A rejected correction or remaining drift is reported as a state
failure instead of starting an unbounded mutation loop.

The RBD lifecycle requires the `rbd` feature and:

- `CEPH_TEST_POOL`, `CEPH_TEST_RBD_NAMESPACE`, `CEPH_TEST_RBD_IMAGE`, and
  `CEPH_TEST_RBD_SNAPSHOT`;
- allowlist entries `pool:<pool>`, `namespace:<pool>/<namespace>`,
  `image:<pool>/<image>`, and `snapshot:<pool>/<image>@<snapshot>`.

It reconciles a dedicated pool, namespace, image metadata, and snapshot. All
four resources must be absent before the test claims them.

The CephFS lifecycle requires the `cephfs` feature and:

- `CEPH_TEST_CEPHFS`, `CEPH_TEST_CEPHFS_HOST`,
  `CEPH_TEST_CEPHFS_DATA_POOL`, `CEPH_TEST_CEPHFS_METADATA_POOL`,
  `CEPH_TEST_CEPHFS_GROUP`, `CEPH_TEST_CEPHFS_SUBVOLUME`, and
  `CEPH_TEST_CEPHFS_SNAPSHOT`;
- allowlist entries `pool:<data-pool>`, `pool:<metadata-pool>`,
  `fs:<filesystem>`, `host:<placement-host>`,
  `cephfs-group:<filesystem>/<group>`,
  `cephfs-subvolume:<filesystem>/<group>/<subvolume>`, and
  `cephfs-snapshot:<filesystem>/<group>/<subvolume>@<snapshot>`.

The placement host must already exist. The lifecycle creates the pools and
filesystem, updates group and subvolume quotas, creates a subvolume snapshot,
then removes the objects in dependency order. Dashboard can finish its CephFS
delete task before cephadm's serve loop has removed the filesystem's MDS
daemons. The filesystem state therefore polls the exact
`mds.<filesystem>` service daemon inventory before it reports convergence. A
daemon that remains until the bounded timeout is an orchestration cleanup
failure rather than a successful lifecycle; inspect the service events and
cephadm logs before retrying. Dashboard exposes daemon start, stop, restart,
and redeploy actions, but no individual daemon-delete endpoint.

The RGW lifecycle requires both `orchestrator` and `rgw` features and:

- `CEPH_TEST_RGW_SERVICE`, using a unique `rgw.saltext-ci-*` name;
- `CEPH_TEST_RGW_HOST`, `CEPH_TEST_RGW_USER`, and `CEPH_TEST_RGW_BUCKET`;
- allowlist entries `service:<service>`, `host:<placement-host>`,
  `rgw-user:<uid>`, and `bucket:<bucket>`.

The host must already exist. The lifecycle deploys the service and waits for a
running daemon, creates and updates an ownership-marked user, creates a bucket,
enables bucket versioning, then removes the bucket, user, and service in that
order.

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

Run one configured destructive scenario through the Nox entry point, supplying
both additional gates and an exact test path:

```console
nox -s live -- --ceph-live-mutate --ceph-live-destructive \
  tests/integration/states/test_live_osd_states.py
```

The Nox session clears ambient `PYTEST_*` options, disables automatic third-party
plugin loading, and validates the selected paths and flags before pytest starts.
This also prevents local debugging settings such as `--showlocals` from exposing
credential-bearing fixture values in a failure report.

Use a narrow test path so the environment and allowlist authorize only the
intended lifecycle. A missing feature, baseline OSD count, pool-delete setting,
identity, allowlist entry, or ownership proof causes a skip or hard failure
before an unsafe cleanup can run.

## Recorded compatibility

On 2026-09-07, the suite was exercised against a disposable three-host, three-OSD
Ceph 20.2.4 Tentacle cluster through a self-signed Dashboard endpoint. The 29
read-only cases covered authentication, health, FSID, summary, monitor data,
hardware data, cephadm host/service/daemon inventory, storage defaults, CRUSH and
erasure profiles, and real Salt execution-module loading. Host registration and
the three baseline OSD services converged idempotently. The RBD, CephFS, and RGW
state lifecycles each passed create, update, repeated apply, and cleanup against
the live cluster.

Ceph 20.2.4 has a Dashboard compatibility defect while an OSD removal is queued:
the cephadm backend returns dictionaries, while the OSD controller dereferences
them as objects. Detailed `GET /api/osd` calls can consequently return HTTP 500.
The OSD state uses the Dashboard individual-flags view, which reads the raw OSD
map, to verify disappearance without interpreting a controller error as success.
The upstream correction is tracked in Ceph commit
[`cf0785951a8a6e1be6bd865a652e8fbb2df2a9c7`](https://github.com/ceph/ceph/commit/cf0785951a8a6e1be6bd865a652e8fbb2df2a9c7).
The same acceptance run confirmed the Dashboard 20.2 device-cleanup limitation
described above: OSD absence does not prove that its backing device is reusable.
