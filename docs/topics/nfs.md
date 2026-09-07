# NFS exports

The `ceph_nfs` execution module manages the public Dashboard
`/api/nfs-ganesha` resources. Deploy the NFS service itself with
`ceph_service`; this module reads NFS clusters and manages the exports backed by
CephFS or RGW.

| Function | Dashboard request | API version |
| --- | --- | --- |
| `clusters` | `GET /api/nfs-ganesha/cluster` | experimental `0.1` |
| `list_exports` | `GET /api/nfs-ganesha/export` | `1.0` |
| `get_export` | `GET /api/nfs-ganesha/export/{cluster_id}/{export_id}` | `1.0` |
| `create_export` | `POST /api/nfs-ganesha/export` | `2.0` |
| `update_export` | `PUT /api/nfs-ganesha/export/{cluster_id}/{export_id}` | `2.0` |
| `delete_export` | `DELETE /api/nfs-ganesha/export/{cluster_id}/{export_id}` | `2.0` |

These list resources are not paginated. They return the complete result and do
not have `offset` or `limit` parameters.

```bash
salt-call --local ceph_nfs.clusters
salt-call --local ceph_nfs.list_exports
salt-call --local ceph_nfs.get_export nfs1 1
```

The compatibility defaults work on Reef and current Ceph. Current Ceph also
supports `ceph_nfs.clusters info=true`, which returns cluster information, and
`ceph_nfs.list_exports cluster_id=nfs1`, which filters on the server. The Reef
controller has neither parameter, so the extension omits both unless the caller
explicitly requests them.

Create and update take structured values. A CephFS export looks like this:

```bash
salt-call --local ceph_nfs.create_export \
  path=/volumes/team/data cluster_id=nfs1 pseudo=/team/data \
  access_type=RW squash=root_squash security_label=false \
  protocols='[4]' transports='["TCP"]' \
  fsal='{"name":"CEPH","fs_name":"cephfs"}' \
  clients='[{"addresses":["192.0.2.0/24"],"access_type":"RO","squash":"root_squash"}]'
```

`fsal.name` is `CEPH` or `RGW`. CephFS requires `fs_name`; when
`security_label=true`, also supply `sec_label_xattr`. An RGW bucket export uses
the bucket name as `path`. An RGW whole-user export uses `path=/` and supplies
`fsal.user_id`. Ceph manages the CephFS `user_id`, CephX key, and RGW access and
secret keys, so those secret fields cannot be submitted.

The API accepts access types `RW`, `RO`, and `NONE`, protocols 3 and 4, and the
TCP and UDP transports. Use protocol 4 for the documented Reef cephadm NFS
service: Reef's cephadm documentation states that only NFSv4 is supported.
Current Ceph also accepts `RDMA` when RDMA is enabled in the NFS service spec;
Reef rejects that transport.

`update_export` is a full public export replacement. Read the export, edit it,
and supply all public fields other than `cluster_id` and `export_id`. Ceph keeps
server-managed FSAL credentials internally. Create, update, and delete use
Dashboard tasks and can return HTTP `202`; the response means accepted, not
converged. Inspect the returned task with `ceph_task`.

Deleting an export requires `confirm=true`:

```bash
salt-call --local ceph_nfs.delete_export nfs1 1 confirm=true
```

This removes client access and the Ganesha export configuration. It does not
delete the backing CephFS data, RGW bucket, or RGW objects.

## Declarative state

Ceph assigns `export_id`, so the `ceph_nfs.present` state uses the stable pair
`cluster_id` and pseudo path (`name`) as its identity. It compares every public
export field, uses a full update when drift exists, waits for an asynchronous
Dashboard task, and reads the export again before reporting success.

```yaml
/team/data:
  ceph_nfs.present:
    - cluster_id: nfs1
    - path: /volumes/team/data
    - access_type: RW
    - squash: root_squash
    - protocols: [4]
    - transports: [TCP]
    - fsal:
        name: CEPH
        fs_name: cephfs
    - clients:
        - addresses: [192.0.2.0/24]
          access_type: RO
          squash: root_squash
```

Removal uses the same logical identity and requires `confirm: true`. Export
listing is filtered locally, which keeps this state compatible with Reef even
though only current Ceph supports the server-side `cluster_id` list filter.

There are several source/OpenAPI differences that affect automation:

- `security_label` is documented as a string by the generated OpenAPI file,
  while the NFS manager validates a boolean and the Dashboard frontend sends a
  boolean.
- The current controller supports the cluster `info` query and export
  `cluster_id` filter, while Reef and the local OpenAPI document omit them.
- The generated create schema omits RGW `fsal.user_id`, although the Dashboard
  frontend sends it for whole-user exports and both controller generations
  accept the nested field.
- The current NFS manager adds RDMA; the Reef manager validates only TCP and
  UDP.

The implementation follows the
[current NFS controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/nfs.py),
the [Reef NFS controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/nfs.py),
the [NFS manager implementation](https://github.com/ceph/ceph/tree/main/src/pybind/mgr/nfs),
and the [Reef NFS service documentation](https://docs.ceph.com/en/reef/cephadm/services/nfs/).
