# Salt Extension for Ceph

`saltext.ceph` manages Ceph through the versioned Dashboard REST API. Cephadm
continues to place and reconcile daemons; Salt describes cluster resources,
calculates drift, invokes cephadm through Dashboard, and verifies the result.
This makes the extension suitable for reviewed GitOps and Infrastructure as Code
workflows without installing a Salt minion on every storage host.

**Status: alpha.** The project has not yet published a package to PyPI. Its API
surface and state contracts can still change before the first release.

## What is included

- Typed execution modules and matching salt-ssh wrappers for the public Dashboard
  controllers: cluster and cephadm, hosts, services, OSDs, pools, CRUSH, CephFS,
  RBD, NFS, iSCSI, SMB, RGW, NVMe-oF, CephX and Dashboard administration,
  observability, tasks, feature availability, the current Dashboard MOTD,
  integrations, and multi-cluster management.
- Declarative states for resources whose current value can be read and compared
  reliably. States support Salt test mode, asynchronous Dashboard tasks, a
  post-write read, and explicit confirmation for destructive changes.
- Exact-target GitOps runners with expected-FSID checks and overlapping-job
  protection.
- Read-only health, task, and certificate beacons with bounded, redacted events.
- A shared synchronous HTTP client with TLS verification, strict profiles,
  request validation, safe errors, token refresh, and wrong-cluster protection.

The [support matrix][support] records the exact boundary between
declarative resources, imperative operations, Reef-compatible endpoints, and
current-only endpoints. The [controller inventory][controllers]
maps the upstream source tree and explains every reviewed exclusion. Private
`/ui-api` routes and CLI-only manager methods are deliberately excluded.

## Deployment model

Install the extension only where Salt calls the Dashboard API: one dedicated
control minion per cluster, a masterless `salt-call --local` node, or a salt-ssh
controller. Ceph cluster hosts do not need Salt for API-based management.

Configure a profile outside the state repository, for example in an encrypted
pillar or protected Salt configuration:

```yaml
ceph:
  profiles:
    default:
      url: https://ceph.example:8443
      username: salt-automation
      password: <resolved by secret management>
      verify: /etc/salt/pki/ceph-dashboard-ca.pem
      expected_fsid: 11111111-1111-1111-1111-111111111111
```

Keep credentials out of Git, command arguments, job caches, and event payloads.
Mutating calls verify `expected_fsid` before the first write. See the
[API client guide][api-client] for the complete profile contract and the
[permissions guide][permissions] for a least-privilege Dashboard role.

A resource can then be managed in ordinary SLS:

```yaml
archive-pool:
  ceph_pool.present:
    - name: archive
    - pool_type: replicated
    - pg_num: 32
    - application_metadata:
        - rbd
```

Plan and apply the same tree through the designated control minion:

```console
salt-run ceph_gitops.plan ceph-control \
  11111111-1111-1111-1111-111111111111 mods='[ceph.cluster]'
salt-run ceph_gitops.apply ceph-control \
  11111111-1111-1111-1111-111111111111 mods='[ceph.cluster]'
```

The [GitOps guide][gitops] covers repository layout, dependencies,
drift checks, explicit deletion, and CI gates. Removing an SLS declaration alone
does not remove the corresponding Ceph resource.

## Install and develop

Until the first release, build or install the checkout in the Python environment
that runs Salt:

```console
git clone https://github.com/glebrodionov94/saltext-ceph.git
cd saltext-ceph
uv venv --python 3.11
uv pip install -e ".[tests,dev,docs,build]" "salt==3006.27"
python -m pytest tests/unit -q
```

The distribution is named `saltext.ceph` and registers a `salt.loader` entry
point. Python 3.10+ and Salt 3006+ are supported package targets. CI exercises
Salt 3006 and 3008; live Dashboard smoke tests are opt-in because they require a
real cluster.

See [installation][installation], [development][development], and
[release][releasing] for the complete workflows. Security reports belong in a
private [GitHub Security Advisory][security], not a public issue.

## Project layout

```text
src/saltext/ceph/
  modules/          Salt execution modules
  states/           Declarative state modules
  utils/ceph/       HTTP client and typed controller adapters
  wrapper/          Controller-side salt-ssh functions
  runners/          Master-side operational and GitOps runners
  beacons/          Read-only transition detectors
tests/               Unit and opt-in live integration tests
docs/                Sphinx guides and generated API reference
changelog/           Towncrier news fragments
tools/               Development and distribution checks
```

The scaffold was generated with
[salt-extension-copier](https://salt-extensions.github.io/salt-extension-copier/),
using [saltext-vault](https://github.com/salt-extensions/saltext-vault) as a
structural reference. The project is licensed under Apache-2.0; see
[LICENSE][license] and [NOTICE][notice].

[api-client]: https://github.com/glebrodionov94/saltext-ceph/blob/main/docs/topics/api-client.md
[controllers]: https://github.com/glebrodionov94/saltext-ceph/blob/main/docs/topics/controller-coverage.md
[development]: https://github.com/glebrodionov94/saltext-ceph/blob/main/docs/topics/development.md
[gitops]: https://github.com/glebrodionov94/saltext-ceph/blob/main/docs/topics/gitops.md
[installation]: https://github.com/glebrodionov94/saltext-ceph/blob/main/docs/topics/installation.md
[license]: https://github.com/glebrodionov94/saltext-ceph/blob/main/LICENSE
[notice]: https://github.com/glebrodionov94/saltext-ceph/blob/main/NOTICE
[permissions]: https://github.com/glebrodionov94/saltext-ceph/blob/main/docs/topics/permissions.md
[releasing]: https://github.com/glebrodionov94/saltext-ceph/blob/main/docs/topics/releasing.md
[security]: https://github.com/glebrodionov94/saltext-ceph/security/policy
[support]: https://github.com/glebrodionov94/saltext-ceph/blob/main/docs/topics/support.md
