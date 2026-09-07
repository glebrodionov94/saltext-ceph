# Dashboard roles

The `ceph_role` execution module manages the roles used to authorize Ceph
Dashboard login users. These roles are separate from CephX capabilities.

## Read and manage roles

```bash
salt-call --local ceph_role.list
salt-call --local ceph_role.get backup-manager
salt-call --local ceph_role.create backup-manager \
  description='Backup operators' \
  scopes_permissions='{"pool":["read"],"rbd-image":["read","create"]}'
salt-call --local ceph_role.update backup-manager \
  description='Backup operators' scopes_permissions='{"pool":["read"]}'
salt-call --local ceph_role.clone backup-manager backup-manager-copy
salt-call --local ceph_role.delete backup-manager-copy confirm=true
```

Every operation accepts `profile`, defaulting to `default`, and returns the common
`status`, `data`, and `headers` envelope. Permission names are `read`, `create`,
`update`, and `delete`. Scope names are validated as bounded identifiers and are
left release-extensible because Ceph adds scopes as features are introduced.

`update` sends the complete permission mapping. Omitting `scopes_permissions` or
passing an empty mapping clears all scope permissions, and omitting `description`
sets it to null. Read the current role first when making a partial conceptual
change. Execution functions are intentionally non-idempotent; reconciliation
belongs in a state module.

Dashboard's built-in system roles appear in `list` and `get`, but Ceph refuses to
update or delete them. Ceph also refuses to delete a custom role while it is
assigned to a user. `clone` copies both description and scope permissions on the
server.

For an unambiguous REST path, this extension accepts letters, digits, dots,
underscores, and hyphens in role names. The Ceph CLI can create some names, such as
names containing `/`, that Dashboard's member URL cannot address reliably.

## Declarative state

`ceph_role.present` manages the complete description and scope-permission mapping.
Permission order is ignored, and empty permission lists have the same canonical
meaning as an omitted scope because Dashboard does not persist empty scopes.

```yaml
backup-manager-role:
  ceph_role.present:
    - name: backup-manager
    - description: Backup operators
    - scopes_permissions:
        pool:
          - read
        rbd-image:
          - read
          - create
```

`ceph_role.absent` is idempotent and requires `confirm: true` for a live delete.
Built-in roles are protected from both updates and deletes. Both functions support
Salt test mode, wait for a Dashboard task when a mutation returns HTTP 202, and
verify the final resource with a fresh list read.

## Source compatibility

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/role.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/role.py),
and Ceph's
[Dashboard user and role documentation](https://docs.ceph.com/en/reef/mgr/dashboard/#user-and-role-management).
Both controller versions expose list, get, create, update, delete, and clone with
API version `1.0`. The local OpenAPI incorrectly describes `scopes_permissions` as
a string; the controller and Dashboard frontend send an object mapping scopes to
permission lists.
