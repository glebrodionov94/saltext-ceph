# RGW daemons and site discovery

The `ceph_rgw_daemon` execution module uses only the public Dashboard API. It
does not configure an RGW cephadm service; deploy that service with
`ceph_service` first.

| Function | Dashboard request | Releases |
| --- | --- | --- |
| `list_daemons` | `GET /api/rgw/daemon` | Reef and current |
| `get_daemon` | `GET /api/rgw/daemon/{svc_id}` | Reef and current |
| `set_multisite_config` | `PUT /api/rgw/daemon/set_multisite_config` | Reef and current |
| `get_site` (`placement-targets`, `realms`, `default-realm`) | `GET /api/rgw/site` | Reef and current |
| `get_site` (`default-zonegroup`) | `GET /api/rgw/site` | current only |

All four operations use API version `1.0`. `get_site` accepts only the queries
implemented by the controller: `placement-targets`, `realms`, `default-realm`,
and, on current Ceph, `default-zonegroup`. A request without one of those
values would produce the controller's HTTP 501 response, so the extension
rejects it before HTTP.

```bash
salt-call --local ceph_rgw_daemon.list_daemons
salt-call --local ceph_rgw_daemon.get_daemon rgw.foo.a
salt-call --local ceph_rgw_daemon.get_site placement-targets daemon_name=rgw.foo.a
```

`set_multisite_config` changes the Dashboard manager module's selected RGW
context. It does not create realms, zonegroups, zones, or daemons. Use
`ceph_rgw_multisite` for the topology and `ceph_service` for daemon placement.

The implementation follows the public
[current RGW controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw.py),
the [Reef RGW controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/rgw.py),
and the [Ceph multisite guide](https://docs.ceph.com/en/latest/radosgw/multisite/).
