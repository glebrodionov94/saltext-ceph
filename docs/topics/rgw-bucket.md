# RGW buckets

`ceph_rgw_bucket` manages the public Dashboard bucket controller. The API is a
Dashboard facade over RGW Admin Ops and S3 operations; it is distinct from an
application's S3 data path.

| Function group | Dashboard request | API version | Releases |
| --- | --- | --- | --- |
| list | `GET /api/rgw/bucket` | `1.1` | Reef and current |
| get/create/update/delete | `/api/rgw/bucket[/{bucket}]` | `1.0` | Reef and current |
| encryption | `/api/rgw/bucket/{set,get,delete}Encryption*` | `1.0` | Reef and current |
| lifecycle | `/api/rgw/bucket/lifecycle` | `1.0` | current only |
| notifications | `/api/rgw/bucket/notification` | `1.0` | current only |
| rate limits | `/api/rgw/bucket[/{bucket_id}]/ratelimit` | `1.0` | current only |

Bucket names and tenant-qualified names are percent-encoded as one route
segment. The list controller has no public marker, offset, or limit parameters.
`stats=true` changes its response from names to bucket mappings.

```bash
salt-call --local ceph_rgw_bucket.list_buckets stats=true
salt-call --local ceph_rgw_bucket.get_bucket tenant/data
salt-call --local ceph_rgw_bucket.create_bucket data alice
salt-call --local ceph_rgw_bucket.update_bucket data bucket-id \
  mfa_token_pin_source=/run/secrets/rgw-mfa-pin
salt-call --local ceph_rgw_bucket.delete_bucket data confirm=true
```

`update_bucket` performs a read before a write when encryption or lifecycle is
omitted. This compensates for the current Ceph controller's defaults: an
omitted `encryption_state` is interpreted as disabled, and an omitted
`lifecycle` enters the lifecycle deletion branch. The adapter reads the bucket
and sends its existing values. It also derives an omitted `uid` from that read,
avoiding a current-controller null-owner failure. Reef's response naturally
omits the current-only lifecycle field. An explicit lifecycle value of `{}` is
a delete operation and requires `confirm_lifecycle_delete=true`. Explicitly
setting `encryption_state=false` removes encryption configuration from the
bucket and requires `confirm_encryption_disable=true`; disabling an existing
replication policy requires `confirm_replication_disable=true`.

Reef requires `uid` on update; current Ceph makes it optional. Current Ceph
adds `replication` to create/update and `lifecycle` to update. Those fields are
omitted unless supplied, preserving the Reef contract.

The encryption configuration changed incompatibly. Current Ceph accepts a
structured `config` mapping for `vault` or `kmip`. Reef accepts flattened
fields. `set_encryption_config reef_legacy=true` selects the Reef payload;
without it the adapter validates the current `VaultConfig` or `KmipConfig`
shape. `config_source` must point to an absolute, regular, non-symlink JSON
file, which keeps Vault/KMIP credentials out of Salt job arguments. MFA PINs
use the same boundary through `mfa_token_pin_source`. Returned tokens,
passwords, certificate keys, and key paths are redacted.
`get_encryption_config include_secrets=true` is the explicit escape hatch.

Both controller overloads that use `{}` as deletion (`set_lifecycle` and
`set_notifications`) require `confirm_delete=true`. All explicit DELETE calls
also require `confirm=true`. Bucket deletion remains subject to Ceph's own
empty-bucket check.

Dashboard does not decorate these RGW methods as asynchronous tasks. The
extension still preserves the HTTP status and body, including a `202` returned
by a particular Ceph build, without claiming that acceptance means convergence.

Sources: [current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw.py),
[Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/rgw.py),
[RGW administration](https://docs.ceph.com/en/latest/radosgw/admin/), and
[bucket notifications](https://docs.ceph.com/en/latest/radosgw/notifications/).
