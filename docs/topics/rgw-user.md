# RGW users

`ceph_rgw_user` exposes the public Dashboard user CRUD, capability, key,
subuser, quota, and rate-limit resources. Every operation uses API version
`1.0`.

| Function group | Dashboard request | Releases |
| --- | --- | --- |
| users | `/api/rgw/user[/{uid}]` | Reef and current |
| emails | `GET /api/rgw/user/get_emails` | Reef and current |
| capability | `/api/rgw/user/{uid}/capability` | Reef and current |
| keys | `/api/rgw/user/{uid}/key` | Reef and current |
| quota | `/api/rgw/user/{uid}/quota` | Reef and current |
| subusers | `/api/rgw/user/{uid}/subuser[/{subuser}]` | Reef and current |
| rate limits | `/api/rgw/user[/{uid}]/ratelimit` | current only |

The controller internally follows RGW's user-list markers until it has the
complete list. It does not expose pagination controls. Current Ceph adds
`detailed=true`; the default omits that query and remains compatible with
Reef. Current Ceph also adds `account_id`, `account_root_user`, and structured
`account_policies` to create/update. These values are sent only when requested.

Tenant-qualified users are identified as `tenant$user` (the state also accepts
`tenant/user` as an input alias). The public Dashboard user-create endpoint has
no `tenant` parameter, including in Ceph 20.2.4. `create_user` and
`ceph_rgw_user.present` reject creation of a missing tenant user before sending
a write. Existing tenant users can still be listed, read, updated, and removed
through their full identity.

```bash
salt-call --local ceph_rgw_user.list_users
salt-call --local ceph_rgw_user.get_user tenant\$alice
salt-call --local ceph_rgw_user.create_user alice Alice generate_key=false
salt-call --local ceph_rgw_user.create_key alice generate_key=false \
  access_key_source=/run/secrets/rgw-access-key \
  secret_key_source=/run/secrets/rgw-secret-key
salt-call --local ceph_rgw_user.delete_user alice confirm=true
```

Credential inputs use `access_key_source` and `secret_key_source`. Each source
must be an absolute path to a regular, non-symlink UTF-8 file on the Salt
execution host. The file content is read only inside the execution process, so
the credential itself is absent from Salt arguments and the job cache. The
same boundary applies to key deletion and subuser creation. Provision these
files outside Git and restrict their filesystem permissions.

User reads and mutations redact `access_key`, `secret_key`, Swift keys, and
nested credential-like fields by default. Set `include_secrets=true` only for
the one call that must retrieve a generated credential. Salt returners and job
caches may retain the visible result, so ordinary GitOps runs should keep the
default.

Every removal requires `confirm=true`: user, capability, key, and subuser.
Detaching an account policy through `account_policies.detach` additionally
requires `confirm_policy_detach=true`.
Quota values accept signed integers because RGW uses negative values to disable
an individual limit. Rate limits accept non-negative values, with zero carrying
the RGW disable/unlimited semantics.

For subuser drift, the state sends the full `uid:subuser` identity required by
the Dashboard update/delete branches. Reconciliation never generates a new
secret for an existing subuser.

The implementation follows the [current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/rgw.py),
and the [Admin Ops documentation](https://docs.ceph.com/en/latest/radosgw/adminops/).
