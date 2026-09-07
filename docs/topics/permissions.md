# Dashboard permissions for automation

Ceph Dashboard authorizes every API request through a static security scope and
one or more of `read`, `create`, `update`, and `delete`. Grant the automation
identity only the scopes used by its state tree. Every declarative resource needs
`read` in addition to its mutation permissions because a state reads before a
change and verifies the resource again afterwards.

## Scope mapping

| Salt area | Dashboard scope |
| --- | --- |
| cephadm hosts, services, daemons, and certificates | `hosts` |
| Cluster marker, upgrades, manager configuration, Dashboard settings, telemetry, and multi-cluster | `config-opt` |
| CephX identities and capabilities | `config-opt` |
| OSD inventory and management | `osd` |
| Pools, CRUSH rules, and erasure-code profiles | `pool` |
| RBD images, namespaces, snapshots, and groups | `rbd-image` |
| RBD mirroring | `rbd-mirroring` |
| CephFS resources | `cephfs` |
| CephFS snapshot mirroring | `cephfs-mirror` |
| iSCSI | `iscsi` |
| NFS | `nfs-ganesha` |
| NVMe-oF | `nvme-of` |
| SMB | `smb` |
| RGW, multisite, and IAM | `rgw` |
| Dashboard users and roles | `user` |
| Monitor and manager inspection | `monitor`, `manager` |
| Cluster logs | `log` |
| Grafana integration | `grafana` |
| Prometheus and Alertmanager proxy | `prometheus` |

Health, summary, task, and performance-counter responses are filtered or checked
against the identity's underlying component permissions. Give a read-only
observer only the component scopes it must see. A beacon needs read permission;
it never needs create, update, or delete.

## Create a dedicated identity

Bootstrap the first automation identity with the Ceph CLI on an already trusted
administration host. For a state tree that manages cephadm hosts/services and
pools, a narrow role can be created as follows:

```console
ceph dashboard ac-role-create salt-gitops
ceph dashboard ac-role-add-scope-perms \
  salt-gitops hosts read create update delete
ceph dashboard ac-role-add-scope-perms \
  salt-gitops pool read create update delete
ceph dashboard ac-user-create salt-automation \
  -i /run/secrets/salt-dashboard-password
ceph dashboard ac-user-set-roles salt-automation salt-gitops
```

Extend the role one scope at a time as the reviewed state tree grows. Imperative
execution functions need the permission associated with their HTTP operation;
for example a read-only inventory command needs only `read`, while deleting a
pool needs `read` for a preflight plus `delete` for the mutation.

Store the password outside Git and expose it to the control minion through a
secret backend or protected configuration. Restrict the Salt job cache and
returner because an explicit `include_secrets=true` read can return credentials.
Avoid using the same identity for interactive Dashboard administration.

Dashboard roles can be managed with `ceph_role` and users with
`ceph_dashboard_user`, but the credential that applies those states must already
have the `user` scope. Keep an independent recovery administrator so a bad role
change cannot lock automation and operators out together.

The authoritative command syntax and predefined roles are in Ceph's
[User and Role Management](https://docs.ceph.com/en/latest/mgr/dashboard/#user-and-role-management)
documentation. Controller decorators in the
[Ceph source tree](https://github.com/ceph/ceph/tree/main/src/pybind/mgr/dashboard/controllers)
define the scope mapping used above.
