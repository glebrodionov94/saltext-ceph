# Declarative RGW states

The RGW states reconcile only fields that a public Dashboard `GET` or `list`
operation can verify. Every mutation is followed by an optional Dashboard task
wait for HTTP `202` and a fresh read. A state fails if the readable projection
does not converge.

| State module and function | Managed projection | Ceph release |
| --- | --- | --- |
| `ceph_rgw_user.present`, `absent` | user identity, display name, email, limits, system/suspended flags, account membership | Reef and current |
| `ceph_rgw_user.subuser_present`, `subuser_absent` | subuser identity and permission | Reef and current |
| `ceph_rgw_user.capability_present`, `capability_absent` | exact capability type and permission; permission drift is a confirmed replacement | Reef and current |
| `ceph_rgw_user.quota_present` | user or bucket quota | Reef and current |
| `ceph_rgw_user.rate_limit_present` | complete per-user rate limit | current only |
| `ceph_rgw_user.managed_policies_present` | complete account-user managed-policy ARN set | current only |
| `ceph_rgw_bucket.present`, `absent` | bucket identity, owner, readable object-lock fields; owner and retention changes are confirmed | Reef and current |
| `ceph_rgw_bucket.versioning_present` | versioning status | Reef and current |
| `ceph_rgw_bucket.encryption_present`, `encryption_absent` | encryption status, algorithm, and optional KMS key ID | Reef and current |
| `ceph_rgw_bucket.lifecycle_present`, `lifecycle_absent` | complete lifecycle JSON document | current only |
| `ceph_rgw_bucket.notifications_present`, `notifications_absent` | complete notification JSON document; absence deletes each readable S3 notification ID | current only |
| `ceph_rgw_bucket.policy_present` | bucket policy JSON document | Reef and current |
| `ceph_rgw_bucket.replication_present` | effective replication enabled status | current only |
| `ceph_rgw_bucket.rate_limit_present` | complete per-bucket rate limit | current only |
| `ceph_rgw_multisite.realm_present`, `realm_absent` | realm identity and optional default selection | Reef and current |
| `ceph_rgw_multisite.zonegroup_present`, `zonegroup_absent` | realm membership, default/master flags, endpoints, and zone membership | Reef and current |
| `ceph_rgw_multisite.zone_present`, `zone_absent` | zonegroup membership, default/master flags, endpoints, tier and sync source fields | Reef and current; tier/sync fields are current additions |
| `ceph_rgw_multisite.placement_present` | zonegroup placement classes, tags, and optional tier data | current only |
| `ceph_rgw_multisite.storage_class_present`, `storage_class_absent` | zone storage-class pool and compression | current only |
| `ceph_rgw_multisite.sync_group_*`, `sync_flow_*`, `sync_pipe_*` | sync policy status, complete zone sets, endpoints and filters | current only |
| `ceph_rgw_topic.present`, `absent` | topic identity and stable delivery metadata | current only |
| `ceph_rgw_iam.account_present`, `account_absent`, `account_quota_present` | account fields and exact numeric quotas | current only |
| `ceph_rgw_iam.role_present`, `role_absent` | Reef global or current account role path, assume policy, and duration | Reef and current |

Salt test mode performs all validation and reads, reports the projected change,
and sends no mutation. For example:

```yaml
rgw-user-alice:
  ceph_rgw_user.present:
    - name: alice
    - display_name: Alice Example
    - email: alice@example.test
    - max_buckets: 100
    - profile: production

rgw-user-alice-quota:
  ceph_rgw_user.quota_present:
    - name: user
    - uid: alice
    - enabled: true
    - max_size_kb: 10485760
    - max_objects: 1000000
    - profile: production

rgw-data-bucket:
  ceph_rgw_bucket.present:
    - name: data
    - uid: alice
    - zonegroup: eu
    - placement_target: hot
    - profile: production

rgw-data-lifecycle:
  ceph_rgw_bucket.lifecycle_present:
    - name: data
    - lifecycle:
        Rules:
          - ID: expire-old-data
            Status: Enabled
            Expiration:
              Days: 90
    - profile: production
```

Deletion, removal, disabling, and replacement operations need explicit
confirmation during a live run. Test mode can still show the proposed change
without confirmation. The relevant parameters are `confirm`,
`confirm_disable`, `confirm_suspend`, `confirm_remove`, `confirm_replace`,
`confirm_owner_change`, and `confirm_lock_change`.
Setting another realm, zonegroup, or zone as default must happen before asking
the old default resource to become non-default, because Ceph's endpoint only
sets a new default. A master zone or zonegroup also cannot be demoted through
the corresponding Dashboard update operation.

Credentials use only `*_source` arguments. Sources must be absolute regular
non-symlink files on the Salt execution host. The state validates a source but
never places its content in `changes`. User keys, subuser keys, zone system
keys, topic push endpoints, and opaque topic data are creation-only where a
state accepts them because Ceph generates, masks, or flattens their read-side
representation.

Sync-policy mutations accept `daemon_name` as their write scope. Although the
read endpoint also accepts `zonegroup_name`, the mutation endpoints do not.
The states reject a non-empty `zonegroup_name` so a read from one zonegroup
cannot accidentally be followed by a write through a daemon in another one.
Select an RGW daemon that belongs to the intended zonegroup instead.

An existing zonegroup's realm binding is not moved automatically. Zone
membership moves are declared through `zonegroup_present`, where removing a
zone requires `confirm_remove=True`. This avoids relying on a zone update whose
read model cannot prove that both the old and new membership changed.

Current Ceph's `PUT /api/rgw/bucket/notification` empty-document branch calls
the internal delete helper without a notification ID. `notifications_absent`
therefore reads and validates all supported S3 notification collections, then
uses the public per-ID `DELETE` operation for each entry. It refuses unknown
non-empty collections rather than claiming complete absence.

The following execution operations intentionally have no declarative state:

- standalone RGW key rotation and deletion, because the normal read boundary
  redacts both credentials and access-key identifiers;
- KMS backend configuration, because Vault/KMIP secret values are masked;
- bucket tags, canned ACL and MFA PIN, because their write model has no exact
  portable read projection;
- realm-token import, system-user creation, sync status and similar commands,
  because they are actions rather than resources;
- IAM role permission policies, because the public Dashboard controller lists
  them but exposes no attach/detach endpoint. Current account-user managed
  policies are managed by `ceph_rgw_user.managed_policies_present` instead;
- bucket-policy absence, because the controller can set and read a policy but
  exposes no public delete operation.

`ceph_rgw_iam.account_quota_present` accepts an integer byte count for
`max_size`. Although `radosgw-admin` accepts unit-bearing input such as `10G`,
the account read model returns bytes. Restricting the state input to decimal
bytes keeps the comparison exact.

The current account controller tests numeric limits with Python truthiness, so
it silently ignores zero on create or update. `account_present` accepts an
already-readable zero but refuses a requested change to zero. Use a supported
non-zero limit or manage that exceptional change outside this state until Ceph
exposes an exact mutation.

The current storage-class removal endpoint has no zonegroup selector and, when
given `zone_name`, removes the class from both the zone and the active
zonegroup. The corresponding absent state requires confirmation and documents
that combined effect; placement and storage-class post-reads still verify the
declared projection.

The projections follow the public controllers in
[Ceph main](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw.py),
[Ceph Reef](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/rgw.py),
and the current
[account controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw_iam.py).
