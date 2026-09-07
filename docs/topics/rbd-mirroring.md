# RBD mirroring

The `ceph_rbd_mirroring` module covers Dashboard's public mirroring summary,
site, pool-mode, bootstrap, and peer resources. RBD image mirroring actions and
snapshot schedules live on `ceph_rbd.create`, `ceph_rbd.update`, and
`ceph_rbd.snapshot_create`, matching the upstream controllers.

```bash
salt-call --local ceph_rbd_mirroring.summary
salt-call --local ceph_rbd_mirroring.get_site_name
salt-call --local ceph_rbd_mirroring.set_site_name site-a
salt-call --local ceph_rbd_mirroring.get_pool_mode rbd
salt-call --local ceph_rbd_mirroring.set_pool_mode rbd image
```

Pool modes common to Reef and current Ceph are `image`, `pool`, and `disabled`.
Current main additionally exposes `init-only`, used when a non-default namespace
on the peer maps to the local default namespace. Disabling pool mirroring also
disables mirroring on its images and requires `confirm=true`.

Current main adds an image-level status resource:

```bash
salt-call --local ceph_rbd_mirroring.image_summary rbd vm-1
```

Omit this call on Reef, where only the cluster-wide summary is public.

## Bootstrap peers without exposing tokens

Bootstrap tokens contain monitor addresses and CephX credentials. They are never
accepted as Salt command arguments or returned in Salt data. Token destinations
and sources must be absolute regular paths; writes are atomic and mode `0600`
where the operating system supports POSIX permissions.

```bash
salt-call --local ceph_rbd_mirroring.create_bootstrap_token \
  rbd /var/lib/salt/rbd-site-a.token

salt-call --local ceph_rbd_mirroring.import_bootstrap_token \
  rbd /var/lib/salt/rbd-site-b.token direction=rx-tx
```

Dashboard names its receive-only direction `rx`; Ceph's command-line guide calls
the equivalent choice `rx-only`. The other Dashboard choice is `rx-tx`.

The legacy peer resources remain available when bootstrap exchange is unsuitable:

```bash
salt-call --local ceph_rbd_mirroring.list_peers rbd
salt-call --local ceph_rbd_mirroring.get_peer rbd PEER-UUID
salt-call --local ceph_rbd_mirroring.create_peer \
  rbd remote mirror mon_host='v2:192.0.2.10:3300' \
  key_source=/var/lib/salt/remote-mirror.key
salt-call --local ceph_rbd_mirroring.update_peer \
  rbd PEER-UUID cluster_name=remote-new
salt-call --local ceph_rbd_mirroring.delete_peer rbd PEER-UUID confirm=true
```

Ceph's peer `GET` response includes its key. The extension strips `key`, `token`,
and password-shaped fields recursively before returning data. Create and update
read optional keys from absolute files. Use `clear_key=true` to clear a stored
peer key; it is mutually exclusive with `key_source`.

## Snapshot-mode mirroring schedules

Create a snapshot-mirrored image and an image-level schedule together:

```bash
salt-call --local ceph_rbd.create vm-1 rbd 10737418240 \
  mirror_mode=snapshot schedule_interval=6h
```

Reef supports image-level add/remove through the image update controller:

```bash
salt-call --local ceph_rbd.update rbd/vm-1 schedule_interval=12h
salt-call --local ceph_rbd.update rbd/vm-1 remove_scheduling=true confirm=true
```

Current main additionally accepts `schedule_level=image|pool|cluster`. A pool or
cluster schedule is still submitted through an existing image resource because
that is how the public Dashboard controller exposes the operation. Intervals use
positive `m`, `h`, or `d` units. A manually requested mirror snapshot is available
through `ceph_rbd.snapshot_create ... mirror_image_snapshot=true`.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rbd_mirroring.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/rbd_mirroring.py),
and the official [RBD mirroring guide](https://docs.ceph.com/en/latest/rbd/rbd-mirroring/).

## Declarative states

The local site name and a pool's exact public mirroring mode are readable and
have direct states:

```yaml
local-rbd-site:
  ceph_rbd_mirroring.site_name_managed:
    - name: site-a

rbd-pool-mirroring:
  ceph_rbd_mirroring.pool_mode_managed:
    - name: rbd
    - mirror_mode: image
```

Modes `disabled`, `image`, and `pool` work on Reef and current Ceph.
`init-only` requires a current Ceph release that publishes that mode. Disabling
pool mirroring requires `confirm: true` because it also disables image
mirroring.

Legacy peers use their unique `cluster_name` as state identity. Duplicate
cluster names are rejected as ambiguous. The state manages only fields that a
subsequent peer GET can verify: `cluster_name`, `client_id`, and `mon_host`.

```yaml
remote-rbd-peer:
  ceph_rbd_mirroring.peer_present:
    - name: site-b
    - pool_name: rbd
    - client_id: mirror
    - mon_host: v2:192.0.2.10:3300
    - key_source: /var/lib/salt/site-b-mirror.key
```

`key_source` is read only when the peer must be created. Dashboard does not
return a key fingerprint, so the state never claims to detect key drift and
never rotates an existing key. The source path and key contents are excluded
from state changes. Deleting a peer requires `confirm: true`.

All mirroring states support test mode, await HTTP 202 tasks, and verify the
public resource after mutation.

## Deliberate state exclusions

Bootstrap token generation and import remain execution calls because they are
secret exchange operations without a readable desired token state. Peer key,
direction, and mirror UUID are not managed: the legacy update route cannot
declaratively set all of them, and Dashboard deliberately withholds the key.
Snapshot schedules and image promote, demote, and resync actions remain in the
execution layer for the same observable-state and operational reasons described
in the RBD image topic.
