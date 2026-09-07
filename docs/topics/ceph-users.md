# CephX users

The `ceph_users` execution module follows Dashboard's `/api/cluster/user`
controller. It manages CephX entities such as `client.backup`; Dashboard login
accounts belong to a different controller.

## Read and manage users

```bash
salt-call --local ceph_users.list
salt-call --local ceph_users.get client.backup
salt-call --local ceph_users.create client.backup \
  '[{"entity":"mon","cap":"allow r"},{"entity":"osd","cap":"allow rw pool=backups"}]'
salt-call --local ceph_users.update client.backup \
  '[{"entity":"mon","cap":"allow r"}]'
salt-call --local ceph_users.delete client.backup confirm=true
```

Every function accepts `profile`, defaulting to `default`, and returns the common
`status`, `data`, and `headers` envelope. `get` uses the collection endpoint because
the controller has no endpoint for retrieving one entity; an absent entity returns
`data: null`. Dashboard masks keys in collection responses, and the extension
applies its own redaction as a second boundary.

`create` and `update` require a non-empty list of objects with exactly `entity`
and `cap`. Capability service names must be unique. `update` replaces the complete
capability set. Read the current value first when making a partial conceptual
change. These execution functions do not provide idempotency; use
`ceph_users.present` to compare and reconcile normalized capability maps.

Only one entity is accepted by `delete`, and permanent removal requires the real
boolean `confirm=true`. This has consistent behavior across Reef
and current Ceph: the current controller additionally accepts comma-separated
entities, while Reef does not. Calling one entity at a time keeps deletion
results attributable to one desired resource.

## Import and export

Ceph keyrings contain reusable credentials. The module therefore uses local files
instead of Salt arguments and returns:

```bash
salt-call --local ceph_users.import_keyring /run/secrets/import.keyring
salt-call --local ceph_users.export_keyring \
  '["client.backup"]' /run/secrets/client.backup.keyring
```

Import reads an absolute, regular, non-symlink UTF-8 file with a 1 MiB limit.
Export requires an absolute path in an existing directory, writes atomically, and
uses mode `0600` on POSIX systems. Existing files are rejected unless
`overwrite=true` is explicit. Salt returns include only the destination and entity
names, never keyring contents. The salt-ssh wrapper follows the same contract, but
paths refer to the controller filesystem.

Protect files after the command finishes and configure Salt job caches and logging
for sensitive operations. The API response still exists briefly in process memory.

## Source compatibility

The implementation was checked against the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/ceph_users.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/ceph_users.py),
and [Dashboard tests](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/tests/test_ceph_users.py).
The local OpenAPI describes export's `entities` as a string, while the controller
code requires a list. The module follows the controller implementation and tests.
All these operations use API version `1.0` in the observed schema.
