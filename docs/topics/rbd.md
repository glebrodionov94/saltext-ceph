# RBD images

The `ceph_rbd` execution module covers every public image, snapshot, trash, and
namespace resource in Ceph Dashboard's `rbd.py` controller. Pass image and trash
specifications in decoded form as `pool/image` or `pool/namespace/image`; the
extension validates each part and performs the URL encoding.

## Images and pagination

The image collection is the one RBD endpoint negotiated as API version `2.0`.
It preserves Dashboard's pool-grouped result and the `X-Total-Count` response
header. `limit=-1` requests all matching images; otherwise `limit` is positive.

```bash
salt-call --local ceph_rbd.list pool_name=rbd offset=0 limit=25 sort=+name
salt-call --local ceph_rbd.list pool_name=rbd namespace=tenant search=vm-
salt-call --local ceph_rbd.get rbd/tenant/vm-1 omit_usage=true
```

The `namespace` list filter and `omit_usage=true` are available on current Ceph
main. Omit them for Reef. All other resource routes use API version `1.0`.

Create accepts byte counts for image size and layout values. Features can be a
JSON list or a comma-separated string. Configuration and metadata are mappings;
a null mapping value removes that individual entry during an update.

```bash
salt-call --local ceph_rbd.create vm-1 rbd 10737418240 \
  namespace=tenant \
  features='["layering","exclusive-lock","object-map","fast-diff"]' \
  configuration='{"rbd_qos_bps_limit":104857600}' \
  metadata='{"owner":"compute"}'

salt-call --local ceph_rbd.update rbd/tenant/vm-1 \
  name=vm-1-renamed metadata='{"ticket":"INC-42"}'
```

`update` sends only explicitly requested fields. Resizing might shrink an image,
so every size change requires `confirm=true`. Changing primary state or mirroring
mode, forcing a resync, disabling image mirroring, and removing a snapshot
schedule also require confirmation.

Copy and clone create new images. `clone_by_snap_id=true` is a current-main
controller option and must be omitted on Reef.

```bash
salt-call --local ceph_rbd.copy rbd/vm-1 backup '' vm-1-copy
salt-call --local ceph_rbd.snapshot_clone rbd/vm-1 daily backup vm-1-clone
salt-call --local ceph_rbd.flatten rbd/vm-1-clone confirm=true
```

`flatten` permanently removes the parent relationship and therefore requires
confirmation. `default_features` and `clone_format_version` expose the two
read-only collection helpers.

## Snapshots

```bash
salt-call --local ceph_rbd.snapshot_create rbd/vm-1 daily
salt-call --local ceph_rbd.snapshot_update rbd/vm-1 daily is_protected=true
salt-call --local ceph_rbd.snapshot_delete rbd/vm-1 daily confirm=true
salt-call --local ceph_rbd.snapshot_rollback rbd/vm-1 daily confirm=true
```

Set `mirror_image_snapshot=true` on `snapshot_create` to ask a snapshot-mode
mirrored image for an immediate mirror snapshot. Snapshot delete and rollback
are irreversible and require exact boolean confirmation.

## Trash and namespaces

```bash
salt-call --local ceph_rbd.move_to_trash rbd/vm-1 delay=86400 confirm=true
salt-call --local ceph_rbd.trash_list pool_name=rbd
salt-call --local ceph_rbd.trash_restore rbd/IMAGE-ID vm-1-restored
salt-call --local ceph_rbd.trash_delete rbd/IMAGE-ID force=true confirm=true
salt-call --local ceph_rbd.trash_purge pool_name=rbd confirm=true

salt-call --local ceph_rbd.namespace_list rbd
salt-call --local ceph_rbd.namespace_create rbd tenant
salt-call --local ceph_rbd.namespace_delete rbd tenant confirm=true
```

Trash purge removes only entries whose deferment has expired. `force=true` on a
single trash deletion bypasses the deferment period, but Ceph still refuses an
image used by clones or containing snapshots. Dashboard only removes an empty
namespace. Every removal route has a local confirmation guard before HTTP.

Create, update, copy, flatten, trash, snapshot, clone, and delete calls can
return HTTP `202`. The returned task envelope means accepted, not completed;
inspect it with `ceph_task` rather than immediately repeating the mutation.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rbd.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/rbd.py),
the [Ceph REST API reference](https://docs.ceph.com/en/latest/mgr/ceph_api/#rbd),
and the [RBD command reference](https://docs.ceph.com/en/reef/man/8/rbd/).

## Declarative states

`ceph_rbd.image_present` manages an image's exact declared public projection.
Size is always declared. Features, create-time layout, image configuration,
metadata, and image mirroring mode are optional; an omitted field is left
unmanaged. A declared configuration mapping represents all image-level
overrides (`source=image`) and does not absorb inherited pool or global values.
Likewise, a declared metadata mapping is the complete desired metadata map.

```yaml
tenant-image:
  ceph_rbd.image_present:
    - name: rbd/tenant/vm-1
    - size: 10737418240
    - features:
      - layering
      - exclusive-lock
      - object-map
      - fast-diff
    - configuration:
        rbd_qos_bps_limit: 104857600
    - metadata:
        owner: compute
    - mirror_mode: snapshot
```

Dashboard can change only a subset of RBD features. A state fails before
mutation when an existing image has drift in a create-only layout field or in
a feature that Dashboard cannot enable or disable. Any size change, mirroring
disable or mirroring-mode switch requires `confirm: true`. Every accepted
asynchronous task is awaited and the image is read again before success is
reported. Credential-shaped configuration and metadata names are rejected so
their values cannot enter Salt state changes.

Namespaces and ordinary image snapshots have dedicated states:

```yaml
tenant-namespace:
  ceph_rbd.namespace_present:
    - name: tenant
    - pool_name: rbd

daily-snapshot:
  ceph_rbd.snapshot_present:
    - name: daily
    - image_spec: rbd/tenant/vm-1
    - is_protected: true
```

Namespace deletion is allowed only when Dashboard reports zero images and
requires confirmation. Snapshot deletion also requires confirmation.
`is_protected` is optional; when omitted, the state manages only existence.
Ceph mirror snapshots report protection as null and cannot use protection
reconciliation.

All these states support Salt test mode and report only their managed public
projection in `changes`.

## Deliberate state exclusions

Copy, clone, flatten, rollback, trash lifecycle, manual mirror snapshots,
promotion, demotion, and resync are operations rather than stable desired
resources, so they remain execution-module calls. Snapshot schedules also stay
in the execution module because the Dashboard image response exposes only one
matching schedule and cannot prove an exact desired set when multiple intervals
exist.
