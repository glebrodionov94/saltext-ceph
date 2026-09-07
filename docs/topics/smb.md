# SMB resources

The `ceph_smb` module manages the public SMB controller introduced after Reef.
It requires a current Ceph release with the `smb` manager module and cephadm SMB
service support.

```console
salt-call --local ceph_smb.list_clusters
salt-call --local ceph_smb.create_cluster resource='{
  "cluster_id":"files","auth_mode":"user",
  "user_group_settings":[{"source_type":"resource","ref":"local-users"}]}'
salt-call --local ceph_smb.create_share resource='{
  "cluster_id":"files","share_id":"home","name":"Home",
  "cephfs":{"volume":"cephfs","path":"/home","provider":"samba-vfs"}}'
```

Domain join passwords are read from an absolute, regular, non-symlink file:

```console
salt-call --local ceph_smb.create_join_auth domain-admin Administrator \
  /run/secrets/smb-domain-password linked_to_cluster=files
```

Local user definitions use a protected JSON file containing `users` and
`groups`. This keeps passwords out of Salt CLI arguments, event data, and job
caches:

```json
{
  "users": [{"name": "alice", "password": "replace-through-secret-management"}],
  "groups": [{"name": "operators"}]
}
```

```console
salt-call --local ceph_smb.create_usersgroups local-users \
  /run/secrets/smb-users.json linked_to_cluster=files
```

All list, get, and mutation returns replace password-like fields with a marker.
Cluster and share mappings reject inline secret fields. Deletes require
`confirm=true`. QoS updates send only declared fields and enforce the limits in
the current controller.

Declarative states reconcile only resources that the public API can read back:

```yaml
files:
  ceph_smb.cluster_present:
    - resource:
        auth_mode: user
        user_group_settings:
          - source_type: resource
            ref: local-users

home:
  ceph_smb.share_present:
    - cluster_id: files
    - resource:
        cluster_id: files
        name: Home
        readonly: false
        cephfs:
          volume: cephfs
          path: /home

home-qos:
  ceph_smb.share_qos:
    - name: home
    - cluster_id: files
    - read_iops_limit: 1000
```

Join-auth and users/groups credentials intentionally have no state function:
Dashboard returns redacted passwords, so a state cannot prove password equality.
Use the file-based execution functions for explicit creation or rotation.

SMB is absent from Reef 18.2.8. The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/smb.py)
and its
[controller tests](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/tests/test_smb.py).
