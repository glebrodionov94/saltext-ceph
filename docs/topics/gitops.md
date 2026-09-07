# GitOps workflow

The extension needs Salt only on the machine that calls Ceph Dashboard. Ceph
hosts do not need minions for API management. Use one control minion per cluster,
or run `salt-call --local` on a dedicated controller. Cephadm remains responsible
for deploying and continuously reconciling daemons on cluster hosts.

## Repository model

Keep SLS files and non-secret pillar data in Git. Store the Dashboard password or
token in an encrypted external pillar, SOPS-rendered file, Vault backend, or
another secret store outside the plain repository. The resolved control-minion
profile has this shape:

```yaml
ceph:
  profiles:
    default:
      url: https://ceph-test.example:8443
      username: salt-automation
      password_file: /run/secrets/ceph-dashboard-password
      verify: /etc/salt/pki/ceph-dashboard-ca.pem
      expected_fsid: 11111111-1111-1111-1111-111111111111
```

The Git-managed profile can safely contain the stable secret path. Provision the
referenced regular, non-symlink file through the host's secret manager with
permissions limited to the Salt process. Credential rotation replaces the
cached Dashboard client on the next profile resolution.

`expected_fsid` is checked by the HTTP client before its first mutation. The
GitOps runner checks the same FSID before compiling a state run, which protects
against a correct credential profile pointing at the wrong cluster.

A state tree can render resource declarations from ordinary pillar data:

```jinja
{% for hostname, host in pillar.get('ceph_hosts', {}).items() %}
ceph-host-{{ hostname }}:
  ceph_host.present:
    - name: {{ hostname | yaml_dquote }}
    - address: {{ host.address | yaml_dquote }}
    - labels: {{ host.get('labels', []) | json }}
{% endfor %}

{% for service_name, spec in pillar.get('ceph_services', {}).items() %}
ceph-service-{{ service_name }}:
  ceph_service.present:
    - name: {{ service_name | yaml_dquote }}
    - service_spec: {{ spec | json }}
    - require:
      - ceph_host: ceph-host-{{ spec.placement.hosts[0] }}
{% endfor %}
```

Use requisites to express dependencies such as host before service, erasure
profile before pool, pool before RBD image, and filesystem before subvolume.
Cephadm performs daemon placement asynchronously, so a service state verifies the
accepted specification rather than waiting for every daemon to become healthy.

## Plan and apply

With a Salt master, target exactly the designated control minion through the
runner:

```console
salt-run ceph_gitops.plan ceph-control \
  11111111-1111-1111-1111-111111111111 mods='[ceph.cluster]'
salt-run ceph_gitops.apply ceph-control \
  11111111-1111-1111-1111-111111111111 mods='[ceph.cluster]'
```

The plan calls `state.apply test=true`. Apply refuses an overlapping state job
and uses `queue=false`. The check is local to one Salt master, so CI should also
serialize runs with one concurrency group per cluster. Do not pass credentials
or inline pillar to the runner; Salt jobs and events can retain arguments.

Masterless operation is sufficient when centralized Salt orchestration is not
needed:

```console
salt-call --local state.apply ceph.cluster test=true
salt-call --local state.apply ceph.cluster
```

## Drift and deletion

Run the plan periodically as drift detection and treat a non-empty planned
change as reviewable output. Health, task, and certificate beacons can emit
events between runs, but they do not mutate Ceph. Use reactors only for bounded
notifications or for starting the same reviewed state pipeline.

Removing an SLS declaration from Git does not delete its remote resource. Add an
explicit `absent` declaration, review the plan, and set the required boolean
confirmation for the apply. This makes destructive intent visible in history.
After deletion has converged, a later commit can remove that `absent` block.

Many changes cannot be rolled back by reverting Git alone. Pool deletion, image
deletion, key rotation, snapshot rollback, and daemon actions may destroy data or
invalidate credentials. Git records the desired configuration and approval; it
does not create a storage backup. Keep normal Ceph backup and recovery procedures
alongside the GitOps workflow.

## Pipeline gates

A practical pipeline performs these stages in order:

1. Render and lint the Salt tree without cluster credentials.
2. Run `ceph_gitops.plan` against the exact control minion and expected FSID.
3. Require review for the plan, especially any `absent` state or replacement.
4. Run `ceph_gitops.apply` in a per-cluster concurrency group.
5. Archive the sanitized Salt result and run a second plan to prove convergence.

The state modules remove credential fields from changes. Some explicit execution
functions can reveal secrets when `include_secrets=true`; keep those calls out of
automated pipelines and restrict Salt job-cache and returner access.
