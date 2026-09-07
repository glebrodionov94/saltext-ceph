# CephFS

The `cephfs` execution module maps the public `/api/cephfs` controllers to Salt
and provides the read/write backend for the declarative `cephfs` state module.
Every execution function accepts an optional `profile` and returns the common
`status`, `data`, and `headers` envelope.

## Filesystems and namespace operations

Create a filesystem by passing Dashboard's MDS service specification as a
mapping. `data_pool` and `metadata_pool` are optional fields available in current
Ceph; omit them for Reef.

```bash
salt-call --local cephfs.list
salt-call --local cephfs.create archive \
  '{"placement":{"hosts":["ceph-01","ceph-02"]}}'
salt-call --local cephfs.get 1
salt-call --local cephfs.clients 1
salt-call --local cephfs.rename archive archive-new confirm=true
salt-call --local cephfs.remove archive-new confirm=true
```

The module also exposes client eviction, MDS counters, directory listing and
creation, quota reads and updates, `statfs`, files, directory snapshots, and path
renaming. CephFS paths must be absolute and may not contain traversal segments.
Quota value `0` removes that limit. `write_file` reads an absolute local UTF-8
file, limited to 16 MiB, so its contents do not need to appear in command arguments.

```bash
salt-call --local cephfs.make_directory 1 /projects/archive
salt-call --local cephfs.set_quota 1 /projects/archive max_bytes=1073741824
salt-call --local cephfs.get_quota 1 /projects/archive
salt-call --local cephfs.create_snapshot 1 /projects/archive nightly-1
```

Destructive execution calls require the real boolean `confirm=true`. This covers
filesystem and directory removal, directory snapshot removal, path rename,
`unlink`, file replacement, and client eviction. A `202` response means
Dashboard accepted an asynchronous task; it does not mean the operation has
converged.

## Subvolumes, groups, and snapshots

Names use a conservative set of letters, digits, `_`, `-`, and `.`. Optional
release-specific create fields belong in the `options` mapping. Explicit fields
such as `vol_name` cannot be replaced through `options`.

```bash
salt-call --local cephfs.group_create archive tenants
salt-call --local cephfs.subvolume_create archive app \
  '{"group_name":"tenants","size":1073741824}'
salt-call --local cephfs.subvolume_info archive app tenants
salt-call --local cephfs.subvolume_snapshot_create archive app nightly-1 tenants
salt-call --local cephfs.subvolume_snapshot_clone \
  archive app nightly-1 restored tenants tenants
```

Removing a subvolume, group, or subvolume snapshot also requires
`confirm=true`.

`snapshot_visibility` and `set_snapshot_visibility` follow the current Ceph
controller and are absent in Reef. On a release without them, Dashboard returns
its normal HTTP error through `CommandExecutionError`.

## Snapshot schedules

Schedule paths embedded in Dashboard routes are percent encoded as one route
segment. Retention policies use Ceph's `count-period` form and `|` between entries,
for example `7-d|12-h`.

```bash
salt-call --local cephfs.schedule_create archive /projects 1h \
  '2026-01-01 00:00:00' retention_policy=7-d
salt-call --local cephfs.schedule_update archive /projects retention_to_add=12-h
salt-call --local cephfs.schedule_deactivate archive /projects 1h \
  '2026-01-01 00:00:00'
```

Removing a schedule or retention entry requires `confirm=true`. Adding a new
retention entry does not.

## Snapshot mirroring

The `/api/cephfs/mirror` controller exists in current Ceph and is absent in Reef.
It covers enable/disable, peers, mirrored directories, checkpoints, daemon status,
and synchronization status.

Bootstrap tokens are reusable credentials. `mirror_create_token` writes the token
atomically to an absolute local file and uses mode `0600` on POSIX. It refuses to
overwrite an existing file unless `overwrite=true`. `mirror_add_peer` reads that
file. Neither operation returns the token to Salt. Under salt-ssh, both paths are
on the controller.

```bash
salt-call --local cephfs.mirror_enable archive
salt-call --local cephfs.mirror_create_token archive client.mirror remote \
  /run/secrets/archive-mirror.token
salt-call --local cephfs.mirror_add_peer archive \
  /run/secrets/archive-mirror.token
salt-call --local cephfs.mirror_add_directory archive /projects
salt-call --local cephfs.mirror_status archive
```

Disabling mirroring and removing peers, directories, or checkpoints require
`confirm=true`.

## Declarative states

The `cephfs` state module reconciles only resources and public fields that it
can read back exactly. Every live mutation handles a Dashboard `202` task and
then reads the resource again before reporting success.

```yaml
archive-filesystem:
  cephfs.filesystem_present:
    - name: archive
    - service_spec:
        placement:
          hosts:
            - ceph-01
            - ceph-02

archive-directory:
  cephfs.directory_present:
    - name: /projects/archive
    - fs_id: 1
    - max_bytes: 1073741824

archive-subvolume:
  cephfs.subvolume_present:
    - name: app
    - volume: archive
    - group_name: tenants
    - size: 1073741824

archive-schedule:
  cephfs.snapshot_schedule_present:
    - name: /projects/archive
    - filesystem: archive
    - schedule: 1h
    - start: 2026-01-01T00:00:00
    - retention:
        d: 7
    - active: true

archive-mirror-path:
  cephfs.mirror_directory_present:
    - name: /projects/archive
    - filesystem: archive
```

The available state functions are:

- `filesystem_present` and `filesystem_absent`
- `directory_present`, `directory_absent`, and directory snapshot variants
- `subvolume_present`, `subvolume_absent`, subvolume group variants, and
  subvolume snapshot variants
- `snapshot_schedule_present` and `snapshot_schedule_absent`
- `mirror_directory_present`, `mirror_directory_absent`, `mirror_peer_present`,
  and `mirror_peer_absent`

Filesystem placement and pool arguments are used only when creating a missing
filesystem. Dashboard's filesystem list does not reproduce the original
service specification, so an existing filesystem is managed by identity only.
Likewise, a mirror peer token `source` is bootstrap-only. Optional peer fields
`client_name` and `remote_filesystem` are compared when declared, but existing
drift fails instead of silently recreating the peer because Dashboard has no
peer update endpoint. The token and its local path never appear in state
changes or comments.

Directory quotas and subvolume/group `size` values are exact byte limits.
Omitting them manages existence only. Lowering a finite limit, or replacing an
unlimited limit with a finite one, requires `confirm: true`. Subvolume/group
sizes must be positive; a directory quota may be `0` to remove that limit.
`snapshot_visibility` is exact when declared and needs current Ceph; omit it on
Reef.

Snapshot schedule states support ordinary absolute filesystem paths. Dashboard
does not provide an exact subvolume/group filter on its list endpoint, so the
state module deliberately excludes relative subvolume and group schedules.
Retention is shared by schedules on the same path; all Salt declarations for
that path must therefore use the same retention mapping. Removing or replacing
a retention entry requires `confirm: true`.

CephFS mirroring states use current Ceph and assume mirroring has already been
enabled. The peer and directory list endpoints cannot reliably distinguish a
disabled filesystem from an enabled one with no objects, so enable/disable stay
as execution operations.

Client eviction, path rename, file write/unlink, subvolume snapshot clone, and
mirror checkpoints are operational actions or one-shot side effects. They do
not have states. In particular, `evict_client` disconnects a live client and is
guarded by `confirm=true`; Salt does not try to make eviction persistent.

## Compatibility boundary

The implementation follows the [current `cephfs.py` controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/cephfs.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/cephfs.py),
the [Dashboard controller tests](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/tests/test_cephfs.py),
and the local OpenAPI document captured from a real cluster. The generated schema
has known type gaps for flexible fields, so controller source and tests take
precedence. Internal `/ui-api/cephfs` endpoints are intentionally excluded.

All observed operations use Dashboard API version `1.0`.
