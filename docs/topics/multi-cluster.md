# Multi-cluster Dashboard connections

`ceph_multi_cluster` covers the public `/api/multi-cluster` controller present in
current Ceph. The controller is absent from Reef, so every operation in this
module is current-only. It configures one Dashboard as a hub for other Dashboard
clusters; it does not join Ceph storage clusters or replace cephadm.

## Connect and inspect

Passwords, reusable cluster tokens, and remote TLS certificates are read from
absolute regular non-symlink files. They are never accepted as Salt command
arguments. With salt-ssh these files are on the controller.

```console
salt-call --local ceph_multi_cluster.connect \
  https://remote.example remote administrator \
  /run/secrets/remote-dashboard-password https://hub.example \
  ssl_verify=true \
  ssl_certificate_source=/etc/salt/pki/remote-dashboard.pem

salt-call --local ceph_multi_cluster.get_config
salt-call --local ceph_multi_cluster.token_status
salt-call --local ceph_multi_cluster.security_config
salt-call --local ceph_multi_cluster.prometheus_api_url
```

`get_config` recursively redacts stored tokens and Prometheus passwords by
default. `include_secrets=true` is an explicit diagnostic escape hatch and can
place credentials in Salt output, job caches, logs, and returners. Keep it out of
automated pipelines.

Remote URLs require HTTPS. `allow_http=true` is available for an isolated test
environment and must be set on calls using either an HTTP remote URL or HTTP hub
URL. URLs cannot contain credentials, queries, fragments, traversal, or an
`/api` suffix. When `ssl_verify=true`, supply the remote Dashboard certificate
file expected by Ceph's current controller. Every connect, reconnect, and edit
call must set `ssl_verify` explicitly. Use `false` only when accepting an
unverified remote certificate is an intentional policy decision.

## Select, reconnect, edit, and delete

```console
salt-call --local ceph_multi_cluster.set_current \
  https://remote.example administrator

salt-call --local ceph_multi_cluster.reconnect \
  https://remote.example administrator \
  password_source=/run/secrets/remote-dashboard-password \
  ssl_verify=true \
  ssl_certificate_source=/etc/salt/pki/remote-dashboard.pem

salt-call --local ceph_multi_cluster.edit \
  remote-fsid https://remote-new.example remote administrator \
  ssl_verify=true \
  ssl_certificate_source=/etc/salt/pki/remote-dashboard.pem

salt-call --local ceph_multi_cluster.delete \
  remote-fsid administrator confirm=true
```

Reconnect accepts exactly one of `password_source` and `cluster_token_source`.
Deletion also updates the remote cluster's `MANAGED_BY_CLUSTERS` setting and
Prometheus targets, so it requires the real boolean `confirm=true`.

There is no declarative multi-cluster state in this release. Dashboard stores an
opaque remote JWT, while password authentication can rotate that token and
perform side effects on both clusters. The API does not provide a stable
credential-free desired projection that a highstate could compare safely.

The remote-cluster workflow internally calls current Dashboard UI endpoints for
CORS and Prometheus credentials. Those calls happen inside Ceph; the extension
does not expose `/ui-api` directly. The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/multi_cluster.py)
and its
[Dashboard frontend client](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/frontend/src/app/shared/api/multi-cluster.service.ts).
All public routes use API version `1.0`.
