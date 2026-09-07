# Dashboard settings

The `ceph_settings` execution module manages settings of the Dashboard manager
module. These are not general Ceph cluster configuration options.

## Read settings

```bash
salt-call --local ceph_settings.list
salt-call --local ceph_settings.list \
  names='["PWD_POLICY_ENABLED","REST_REQUESTS_TIMEOUT"]'
salt-call --local ceph_settings.get PWD_POLICY_ENABLED
```

Names may use Ceph's uppercase underscore spelling or lowercase hyphens and are
normalized to uppercase underscores. A filtered list becomes the controller's
comma-separated `names` query parameter.

Settings whose names contain `PASSWORD`, `SECRET`, `TOKEN`, or `KEY` return the
marker `***********` for both `default` and `value`, plus `redacted: true`.
Credential-like keys nested in a structured setting are masked recursively. This
is stricter than the Ceph controller, which returns raw settings to authorized
clients.

## Set and reset values

```bash
salt-call --local ceph_settings.set REST_REQUESTS_TIMEOUT value=60
salt-call --local ceph_settings.set GRAFANA_API_PASSWORD \
  source=/run/secrets/grafana-password
salt-call --local ceph_settings.bulk_set \
  values='{"REST_REQUESTS_TIMEOUT":60,"PWD_POLICY_ENABLED":true}' \
  secret_sources='{"GRAFANA_API_PASSWORD":"/run/secrets/grafana-password"}'
salt-call --local ceph_settings.delete REST_REQUESTS_TIMEOUT
```

Credential-like names require `source`, an absolute local regular file. They are
rejected in the ordinary `value` and `values` arguments. Non-secret settings use
`value` or the `values` mapping. `bulk_set` sends one request after all names,
values, and files pass validation. Mutation returns include names only, never
values. With salt-ssh, secret paths refer to the controller filesystem.

`delete` invokes Dashboard's DELETE member operation; it resets the option to its
declared default rather than removing an option definition. Setting values to
null is rejected so reset remains explicit.

Dashboard converts stored strings according to each option's declared type. Use
the `type` field from `get` or `list` when choosing a JSON boolean, integer, list,
mapping, or string. Execution functions submit changes directly and do not
compare current values.

## Declarative state

`ceph_settings.managed` performs a type-exact JSON comparison, changes a value only
when it differs, and verifies the stored value after the write.

```yaml
dashboard-request-timeout:
  ceph_settings.managed:
    - name: REST_REQUESTS_TIMEOUT
    - value: 60

reset-dashboard-request-timeout:
  ceph_settings.default:
    - name: REST_REQUESTS_TIMEOUT
    - confirm: true
```

`ceph_settings.default` resets an overridden setting to the server-reported
default and requires `confirm: true` outside test mode. Mutations returning HTTP
202 are followed through `ceph_task.wait`, and both states perform a fresh read
before reporting success.

The state intentionally rejects credential-like setting names and structured
values whose keys contain `PASSWORD`, `SECRET`, `TOKEN`, or `KEY`. Dashboard masks
those values, so an exact current-versus-desired comparison is impossible and a
state could only rotate them on every run or claim false convergence. Use the
execution module with a `source` file for an explicit credential rotation. If a
server response is marked as redacted, the state fails with empty changes rather
than placing the desired value on the Salt event bus.

## Source compatibility

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/settings.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/settings.py),
and the [settings definitions](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/settings.py).
The local OpenAPI omits the dynamic request body for bulk update and narrows
setting values to strings or booleans. The controller accepts keyword mappings
and settings declare their own native types. All operations use API version
`1.0`.
