# RGW accounts and roles

`ceph_rgw_iam` covers two public Dashboard contracts. Reef has global role
routes. Current Ceph has account management and moves roles below an account.

| Function group | Dashboard route | Availability |
| --- | --- | --- |
| roles without `account_id` | `/api/rgw/roles` | Reef |
| roles with `account_id` | `/api/rgw/accounts/{account_id}/roles` | current |
| accounts | `/api/rgw/accounts` | current only |
| account quota | `/api/rgw/accounts/{account_id}/quota[/status]` | current only |

All routes use API version `1.0`. Passing `account_id` is the explicit contract
selector for role list/create/update/delete. `get_role` is current-only and
always requires it. The extension does not probe one route after another,
because retrying a mutation across versioned routes is unsafe.

```bash
# Reef role
salt-call --local ceph_rgw_iam.create_role reader /teams/ \
  role_assume_policy_doc='{"Version":"2012-10-17","Statement":[]}'

# Current account and account-scoped role
salt-call --local ceph_rgw_iam.create_account team
salt-call --local ceph_rgw_iam.create_role reader /teams/ account_id=RGW12345678901234567
```

The Dashboard role update value is in hours and is validated from 1 through 12;
the controller converts it to seconds for RGW. Role and account deletion
require `confirm=true`. Account quota sizes remain strings so values such as
`10G` and `-1` retain the semantics of `radosgw-admin`.

Accounts and the RGW IAM API were added in Squid. The Dashboard account
controller is in `rgw_iam.py` on current main and absent from Reef. This module
manages the administrator-facing Dashboard API. The S3-compatible IAM API used
by account root users is served by RGW itself and is outside this extension's
Dashboard connection profile.

Sources: [current account controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw_iam.py),
[current RGW controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw.py),
[Reef RGW controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/rgw.py),
[user accounts](https://docs.ceph.com/en/latest/radosgw/account/), and
[RGW IAM API](https://docs.ceph.com/en/latest/radosgw/iam/).
