# RADOS pools

The `ceph_pool` execution module covers every public resource operation from the
Dashboard `/api/pool` controller. All operations use API version `1.0`.

```bash
salt-call --local ceph_pool.list
salt-call --local ceph_pool.list attrs='["pool_name","type","size"]' stats=true
salt-call --local ceph_pool.get volumes stats=true
salt-call --local ceph_pool.configuration volumes
```

`attrs` accepts a list or comma-separated string. Dashboard always includes
`pool_name`; `stats=true` requests the more expensive runtime statistics path.
`get` also includes the pool's RBD configuration. The separate `configuration`
operation returns only those RBD metadata entries.

Pool creation keeps the stable controller parameters explicit and carries the
extensible `**kwargs` pool settings in `options`:

```bash
salt-call --local ceph_pool.create volumes 32 replicated \
  application_metadata='["rbd"]' \
  rule_name=replicated_rule \
  rbd_configuration='{"rbd_qos_bps_limit":1048576}' \
  options='{"size":3,"min_size":2,"pg_autoscale_mode":"on"}'

salt-call --local ceph_pool.create archive 16 erasure \
  erasure_code_profile=ec42 \
  flags='["ec_overwrites"]' \
  application_metadata='["rgw"]'
```

`pool_type` is `replicated` or `erasure`, and `pg_num` is a positive integer.
`options` accepts the scalar values forwarded by Dashboard to `osd pool set`,
including `size`, `min_size`, `pg_num`, quotas, autoscaling, and compression
properties. Controller-owned keys cannot be smuggled through this mapping.
`rbd_configuration` is an RBD option mapping; a null value removes an existing RBD
configuration entry during update.

```bash
salt-call --local ceph_pool.update volumes \
  new_name=volumes-v2 \
  application_metadata='["rbd"]' \
  options='{"pg_num":64,"size":3}'
```

Update only sends explicitly supplied values. An empty `application_metadata`
list disables every application currently attached to the pool. Dashboard's
`ec_overwrites` flag path enables that flag but exposes no corresponding clear
operation. Use `compression_mode=unset` in `options` to request Dashboard's
compression removal behavior. Renaming is exposed as `new_name` rather than the
controller's ambiguous body key `pool`.

Current Ceph accepts the optional `rbd_mirroring` boolean and reports inherited
mirroring schedule information on reads. Reef does not implement that pool
parameter, so it is omitted unless explicitly supplied. Other pool operations
are compatible with both controller versions.

```bash
salt-call --local ceph_pool.delete obsolete-pool confirm=true
```

Delete permanently removes the pool and its data. The extension requires the
real boolean `confirm=true` before asking Dashboard to perform its own Ceph-side
confirmation. Create, update, and delete can return an asynchronous
`202` task; acceptance does not mean PG convergence has finished.

The generated OpenAPI document can show only the inherited `RBDPool.create`
default instead of the full `Pool.create` body. The extension follows the public
controller signature and Dashboard frontend payload.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/pool.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/pool.py),
and the [Ceph pool documentation](https://docs.ceph.com/en/reef/rados/operations/pools/).
