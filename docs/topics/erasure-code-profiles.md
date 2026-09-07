# Erasure-code profiles

The `ceph_erasure_code_profile` execution module manages the public Dashboard
`/api/erasure_code_profile` resource.

```bash
salt-call --local ceph_erasure_code_profile.list
salt-call --local ceph_erasure_code_profile.get ec42
salt-call --local ceph_erasure_code_profile.create ec42 \
  settings='{"plugin":"jerasure","k":4,"m":2,"crush-failure-domain":"host"}'
salt-call --local ceph_erasure_code_profile.delete ec42 confirm=true
```

`settings` is a mapping because erasure-code plugins accept different parameters
and common Ceph keys such as `crush-failure-domain` are not Python identifiers.
String and numeric values are passed to the Dashboard controller unchanged. An
empty mapping lets Ceph apply its server-side defaults.

The Dashboard endpoint does not expose Ceph's force flags. The module therefore
rejects a `force` setting instead of suggesting that it can safely overwrite an
existing profile. There is no update endpoint. The declarative state treats
profiles referenced by pools as immutable and requires an explicit confirmed
replacement workflow for incompatible changes.

Deletion can fail when a pool references the profile. Ceph also leaves an
associated CRUSH rule in place after deleting a profile, so callers must manage
that rule separately. Deletion requires the real boolean `confirm=true`.

All operations use Dashboard API version `1.0` and return the common `status`,
`data`, and `headers` envelope. The internal `/ui-api/erasure_code_profile/info`
presentation helper is excluded.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/erasure_code_profile.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/erasure_code_profile.py),
and the [Ceph erasure-code profile documentation](https://docs.ceph.com/en/reef/rados/operations/erasure-code-profile/).
