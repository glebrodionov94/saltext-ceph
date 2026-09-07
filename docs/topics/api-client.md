# API client and salt-ssh wrapper

The extension provides a synchronous Dashboard HTTP client, resource execution
modules, declarative states, runners and beacons. `ceph.query` and
`ceph.clear_cache` are low-level **salt-ssh** wrappers. Install the extension in
the Python environment that runs Salt.

`wrapper/` has Salt's specific meaning: functions executed on the salt-ssh
controller. It is not the HTTP abstraction layer. The reusable client lives in
`saltext.ceph.utils.ceph` and is shared by the execution, wrapper, runner, state,
and beacon layers.

## Connection profiles

Configure the controller, for example in `/etc/salt/master.d/ceph.conf` when using
the default salt-ssh configuration directory:

```yaml
ceph:
  profiles:
    default:
      url: https://ceph.example:8443
      username: salt-automation
      password: <supply-through-your-secret-management-system>
      verify: /etc/salt/pki/ceph-ca.pem
      connect_timeout: 5
      read_timeout: 30
```

The URL is the Dashboard root, **without `/api`**. A reverse-proxy prefix such as
`https://ceph.example/dashboard` is supported. `verify` defaults to `true`, using
the Requests CA bundle; a CA file path overrides it. Explicit `verify: false`
disables certificate verification. Plain HTTP requires `allow_http: true`.
Timeouts are positive seconds for connection establishment and socket reads;
they are not an overall deadline for a Ceph operation.

Alternatively, replace both `username` and `password` with `token`. A configured
token is used as-is and cannot be refreshed by the client. Using both methods is
an error. Profile settings reject unknown keys to catch configuration typos.

Keep credential values out of Git and command-line arguments. This extension
does not fetch secrets from Vault or another secret manager itself. For salt-ssh,
profiles are read only from the controller's options, never from a roster target's
pillar. Python consumers explicitly supply their options and pillar; a complete
pillar profile takes precedence over the matching options profile. Profiles are
replaced as a whole, never merged across sources.

## salt-ssh

Examples for a POSIX shell; the inner quotes preserve the API version as a string
through Salt's argument parser:

```bash
salt-ssh ceph-admin ceph.query /api/health/minimal api_version='"1.0"'
salt-ssh ceph-admin ceph.query /api/host api_version='"1.3"' params='{"offset": 0, "limit": 20}'
salt-ssh ceph-admin ceph.query /api/service api_version='"2.0"'
salt-ssh ceph-admin ceph.clear_cache
```

Use a single designated roster target for cluster-level calls. A salt-ssh command
targeting multiple entries invokes the wrapper for each entry, which can repeat
the same cluster operation. The HTTP connection originates on the controller;
the roster target is not used as the Dashboard address.

`query` accepts `method` (default `GET`), `params` for query parameters, `data` for
a JSON body, and `profile` (default `default`). Every method other than GET and
HEAD requires the real boolean `confirm=True`; strings such as `"true"` are
rejected. It returns an envelope:

```json
{"status": 200, "data": {"health": {"status": "HEALTH_OK"}}, "headers": {"content-type": "application/json"}}
```

This is a low-level API operation: it provides no diff, idempotency or convergence
checking. Prefer the typed execution modules and states. HTTP mutations are
rejected with Salt's `test` option enabled even when confirmed. Successful
response bodies are returned unchanged and can contain sensitive resource data;
choose your Salt returners and access controls accordingly.

## Authentication module

The authentication module follows Ceph's public `auth.py` controller:

```bash
salt-call --local ceph_auth.login
salt-call --local ceph_auth.check
salt-call --local ceph_auth.logout
```

The same names are available as salt-ssh wrappers. `login` accepts an optional
positive integer `ttl` in hours on Ceph releases that support it. It is omitted by
default because Reef's login controller has no `ttl` argument. Login returns the
username, permissions and other public session metadata, while removing the JWT.

`check` validates the current token and adds `authenticated: true` when Ceph
returns an identity, or `false` when the controller responds with its login data.
The Ceph endpoint defines the JWT as a query parameter, so access and reverse-proxy
logs must omit query strings. `logout` asks Ceph to revoke the JWT and then always
forgets the local token. A network failure makes the server-side result unknown.
With a static-token profile, logout revokes that configured token; it will remain
unusable until configuration supplies another token.

## Python and Salt modules

```python
from saltext.ceph.utils import ceph

# A Salt loader supplies __opts__, __pillar__ and __context__.
client = ceph.get_client(__opts__, __pillar__, __context__, profile="default")
response = client.request("GET", "/api/host", api_version="1.3")
hosts = response.data
status = response.status
```

Utilities are imported directly. Salt 3006's utility loader does not discover
extension entry points automatically; this code does not depend on that mechanism.
Users deliberately configuring `utils_dirs` can also load `ceph.get_client` and
`ceph.clear_cache` through `__utils__`.

Clients and JWTs are cached only in the caller's in-memory context. Changing a
resolved profile closes and replaces its cached session. Removing or invalidating
a profile discards the old session on the next lookup. Clients are synchronous
and must not be shared between threads. Call `ceph.clear_cache(__context__)` to
close one session, or pass `profile=None` to close all. Clearing is local: it does
not revoke a JWT on the Ceph server.

## Protocol behavior

- Each operation requires an explicit API version. The observed local schema uses
  `1.3` for `GET /api/host`, `2.0` for `GET /api/service`, and `1.0` for health and
  authentication. These values are examples from that schema, not universal
  compatibility claims. The client sets Ceph's versioned `Accept` header.
- Username/password authentication obtains a JWT from `POST /api/auth`. It is
  reused until rejected. A GET/HEAD receiving 401 can log in and retry once.
  Mutations and transport failures are never retried automatically. After a write
  returns 401, the next call obtains a fresh token; a configured token is never
  silently replaced. Failed logins are not retried.
- HTTP 202 and the task payload are preserved. Callers must inspect task status
  or reread the resource later. No task polling or automatic pagination occurs.
  `x-total-count`, when present, is included in response headers.
- HTTP errors raise `APIError` with a numeric `status`; the SSH wrapper converts
  this to a Salt `CommandExecutionError` with the status in its extra information.
  Network/TLS errors and invalid protocol responses have separate exception types.
  Errors omit server bodies and transport exception text because these can contain
  credentials or server tracebacks. Mutations may have succeeded before a timeout.
- Redirects are refused. Configure a stable endpoint routed to the active mgr,
  or update the profile after failover. There is no automatic mgr discovery.
  Environment proxies, `.netrc`, and environment CA overrides are disabled; use
  the explicit profile `verify` setting. Cookies do not supplement bearer auth.
- Requests accept `/api/` resource paths only. Authentication endpoints are
  managed privately so that login tokens are not exposed in generic Salt returns.
  Embedded queries, fragments, traversal and ambiguous encoded paths are rejected.

## References and validation scope

The local `openapi.json` informed endpoint versions and response handling. It
remains an ignored reference file and is neither bundled nor required at runtime.
The generated schema contains loose or inconsistent types, so it is not used to
generate resource models or claim that successful responses conform to a schema.

Protocol references: [Ceph REST API](https://docs.ceph.com/en/reef/mgr/ceph_api/),
[Ceph authentication controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/auth.py),
and [saltext-vault's client](https://github.com/salt-extensions/saltext-vault/blob/main/src/saltext/vault/utils/vault/client.py)
and [SSH wrapper](https://github.com/salt-extensions/saltext-vault/blob/main/src/saltext/vault/wrapper/vault.py).

Tests use synthetic responses, actual Salt loaders and a loopback HTTP server.
They require no Ceph credentials and make no requests to a live cluster. Live
Dashboard compatibility, real TLS deployment and end-to-end salt-ssh operation
still need validation against a test cluster.
