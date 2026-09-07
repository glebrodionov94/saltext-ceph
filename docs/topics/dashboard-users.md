# Dashboard login users

The `ceph_dashboard_user` execution module manages interactive Ceph Dashboard
accounts. For CephX entities such as `client.backup`, use `ceph_users` instead.

## Read and manage accounts

```bash
salt-call --local ceph_dashboard_user.list
salt-call --local ceph_dashboard_user.get operator
salt-call --local ceph_dashboard_user.create operator \
  password_source=/run/secrets/operator-password \
  name='Storage operator' email=operator@example.com roles='["read-only"]'
salt-call --local ceph_dashboard_user.update operator \
  name='Storage operator' roles='["read-only"]' enabled=true
salt-call --local ceph_dashboard_user.delete operator confirm=true
```

Every operation accepts `profile`, defaulting to `default`, and returns the common
`status`, `data`, and `headers` envelope. User responses never contain `password`,
`old_password`, `new_password`, or token fields. The extension removes those
fields even if a server regression unexpectedly returns one.

`create` and `update` accept `password_source`, an absolute local regular file that
must not be a symlink and is limited to 1 MiB. Trailing CR/LF characters are
removed so a conventional one-line secret file does not add a newline to the
password. The file path can appear in a Salt job, but its contents are not a Salt
argument or return value. With salt-ssh, the path is on the controller.

The controller's `update` operation replaces all mutable fields in one request.
Its defaults clear `name`, `email`, roles, and password expiration, while
`pwd_update_required` defaults to false. Supply every field that must remain set.
`roles=[]` explicitly removes all roles. The controller prevents disabling or
deleting the currently authenticated account.

Password expiration is a Unix timestamp. Ceph rejects an expiration date in the
past. Account creation defaults to `enabled=true` and
`pwd_update_required=true`.

## Password policy and self-service change

```bash
salt-call --local ceph_dashboard_user.validate_password \
  /run/secrets/proposed-password username=operator
salt-call --local ceph_dashboard_user.change_password operator \
  /run/secrets/old-password /run/secrets/new-password
```

`validate_password` returns only `valid`, `credits`, and `valuation`. An optional
`old_password_source` supports the policy that rejects password reuse.
`change_password` requires the API profile to authenticate as `username`; Ceph
does not permit one logged-in Dashboard user to invoke this endpoint for another.
Its Salt return contains only the username and HTTP metadata.

Disable Dashboard API request-payload auditing when using password endpoints if
the cluster audit configuration would otherwise retain request bodies. Ceph
documents this with `ceph dashboard set-audit-api-log-payload false`.

## Declarative state

`ceph_dashboard_user.present` manages all public account fields as one complete
declaration. Use `display_name` for Dashboard's human-readable `name` field because
Salt reserves the state function's `name` for the username.

```yaml
dashboard-operator:
  ceph_dashboard_user.present:
    - name: operator
    - password_source: /run/secrets/operator-password
    - display_name: Storage operator
    - email: operator@example.com
    - roles:
        - read-only
    - enabled: true
    - pwd_update_required: true
```

`password_source` is bootstrap-only: it is read and sent when the account is
absent and must be created. Dashboard never returns the stored password hash and
offers no password equality endpoint. The state therefore cannot detect password
drift and never sends a password while updating an existing account. Rotate an
existing password as an explicit operation outside this state. This avoids a
state that reports false idempotence or rotates the password on every highstate.

The password value and its source path never appear in state comments or changes.
Unexpected password or token fields in a mocked or regressed server response are
also discarded by the state's public-field projection. `ceph_dashboard_user.absent`
requires `confirm: true` for a live delete. Both functions support test mode, HTTP
202 task waiting, and a final list read.

## Source compatibility

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/user.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/user.py),
the [Dashboard frontend client](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/frontend/src/app/shared/api/user.service.ts),
and Ceph's
[Dashboard account documentation](https://docs.ceph.com/en/reef/mgr/dashboard/#user-and-role-management).
The local OpenAPI describes `roles` and `pwdExpirationDate` as strings, while the
controller consumes a role list and an integer timestamp. All observed operations
use API version `1.0`.
