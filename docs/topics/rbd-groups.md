# RBD groups

The `ceph_rbd_group` execution module implements the RBD group and group-snapshot
resources added to the current Ceph `rbd.py` controller. These routes are absent
from Reef and should only be called after upgrading to a Ceph release that
publishes `/api/block/pool/{pool_name}/group`.

Groups hold images from the same pool and namespace:

```bash
salt-call --local ceph_rbd_group.list rbd namespace=tenant
salt-call --local ceph_rbd_group.create rbd database namespace=tenant
salt-call --local ceph_rbd_group.add_image rbd database db-1 namespace=tenant
salt-call --local ceph_rbd_group.get rbd database namespace=tenant
salt-call --local ceph_rbd_group.update rbd database database-primary namespace=tenant
salt-call --local ceph_rbd_group.remove_image \
  rbd database-primary db-1 namespace=tenant confirm=true
salt-call --local ceph_rbd_group.delete \
  rbd database-primary namespace=tenant confirm=true
```

Removing an image changes only group membership; it does not delete the image.
The extension still requires confirmation because it changes the consistency
set. Ceph only deletes an empty group.

Group snapshots capture a crash-consistent point across every member image:

```bash
salt-call --local ceph_rbd_group.snapshot_list rbd database namespace=tenant
salt-call --local ceph_rbd_group.snapshot_create \
  rbd database before-upgrade namespace=tenant
salt-call --local ceph_rbd_group.snapshot_get \
  rbd database before-upgrade namespace=tenant
salt-call --local ceph_rbd_group.snapshot_update \
  rbd database before-upgrade retained namespace=tenant
salt-call --local ceph_rbd_group.snapshot_rollback \
  rbd database retained namespace=tenant confirm=true
salt-call --local ceph_rbd_group.snapshot_delete \
  rbd database retained namespace=tenant confirm=true
```

Snapshot create, rename, delete, and rollback can return an HTTP `202` task.
Rollback and delete require exact confirmation before any request is sent.

The route and payload contract follows the
[current Ceph controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rbd.py#L510).

## Declarative states

`ceph_rbd_group.present` can manage only group existence or the exact complete
membership. Omit `images` to leave membership unmanaged. Pass an explicit list,
including an empty list, to reconcile the complete member set.

```yaml
database-consistency-group:
  ceph_rbd_group.present:
    - name: database
    - pool_name: rbd
    - namespace: tenant
    - images:
      - db-1
      - db-2
    - confirm: true
```

Removing a member requires `confirm: true` because it changes the consistency
set. It does not delete the RBD image. `ceph_rbd_group.absent` first removes all
members and then deletes the empty group; the whole operation requires
confirmation.

Group snapshots can be managed by existence:

```yaml
database-before-upgrade:
  ceph_rbd_group.snapshot_present:
    - name: before-upgrade
    - pool_name: rbd
    - group_name: database
    - namespace: tenant
```

Snapshot deletion requires `confirm: true`. Every group state supports test
mode, waits for each HTTP 202 task, and reads the final public resource before
reporting success. These states require the current-Ceph group routes and are
not compatible with Reef.

## Deliberate state exclusions

Group and group-snapshot rename remain explicit execution calls: a desired name
alone cannot safely identify the prior resource. Snapshot creation flags are
not returned by the public GET route, so the state uses the default flags and
does not pretend to manage them. Group-snapshot rollback is an operational,
destructive action and has no declarative state.
