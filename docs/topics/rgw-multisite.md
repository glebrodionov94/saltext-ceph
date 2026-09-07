# RGW multisite

`ceph_rgw_multisite` manages public realm, zonegroup, zone, and current sync
policy endpoints. It deliberately excludes the `/ui-api/rgw/multisite`
controller: migration/setup wizards, credential restart, port discovery, and
UI status are not stable public automation APIs.

All operations use Dashboard API version `1.0`.

| Resource | Dashboard route | Reef | current |
| --- | --- | --- | --- |
| realm | `/api/rgw/realm` | CRUD, topology, tokens/import | plus `replicable` and optional import tier |
| zonegroup | `/api/rgw/zonegroup` | CRUD and topology | plus placement/storage-class operations |
| zone | `/api/rgw/zone` | CRUD, pools, system user, user list | plus tier/sync, realm filter, storage classes |
| sync policy | `/api/rgw/multisite/sync-*` | no public controller | status, groups, flows, and pipes |

```bash
salt-call --local ceph_rgw_multisite.list_realms
salt-call --local ceph_rgw_multisite.create_realm production default=true
salt-call --local ceph_rgw_multisite.create_zonegroup production global
salt-call --local ceph_rgw_multisite.create_zone primary global master=true
salt-call --local ceph_rgw_multisite.import_realm_token \
  /run/secrets/ceph-realm-token secondary 8080
```

Sync flows and pipes use mappings with exactly two keys, `added` and `removed`.
Each value is a list of zone names; `*` is accepted as RGW's wildcard. A
directional flow requires source and destination zones. A symmetrical flow
requires the change mapping. Group status follows Ceph's `enabled`, `allowed`,
or `forbidden` model.

```bash
salt-call --local ceph_rgw_multisite.create_sync_flow mirror symmetrical group1 \
  zones='{"added":["zone-a","zone-b"],"removed":[]}'
salt-call --local ceph_rgw_multisite.create_sync_pipe group1 pipe1 \
  source_zones='{"added":["*"],"removed":[]}' \
  destination_zones='{"added":["*"],"removed":[]}'
```

A non-empty `removed` list on flow or pipe updates requires
`confirm_remove=true`. Removing zones from a zonegroup uses the same guard.

Realm tokens and system-user/zone credentials are redacted by default.
`get_realm_tokens` hides the entire token collection because the scalar value
is itself a bootstrap credential. Use `include_secrets=true` only for a
controlled handoff. `import_realm_token` takes `realm_token_source`, an
absolute path to a regular, non-symlink file. Zone credentials similarly use
`access_key_source` and `secret_key_source`, keeping their values out of Salt
job arguments. `import_realm_token` accepts a placement string or mapping;
Reef requires it, while current Ceph permits omission.

Realm, zonegroup, zone, sync group, flow, pipe, and storage-class removal all
require `confirm=true`. Zonegroup and zone deletion also carry an independent
`delete_pools` boolean and an explicit `pools` list. This prevents a generic
delete approval from silently expanding to data-pool removal.

Ceph requires zonegroup-level sync-policy changes on the master zone and a
period update/commit. Bucket-level policy changes are applied dynamically. The
Dashboard controller performs its own period updates in some paths; operators
should still verify the resulting period and sync state.

Sources: [current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw.py),
[Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/rgw.py),
[multisite guide](https://docs.ceph.com/en/latest/radosgw/multisite/), and
[sync-policy documentation](https://docs.ceph.com/en/latest/radosgw/multisite-sync-policy/).
