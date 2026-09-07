# Cephadm services

The `ceph_service` execution module manages the public Dashboard `/api/service`
resource. A service is the declarative group of daemons maintained by the Ceph
orchestrator.

```bash
salt-call --local ceph_service.known_types
salt-call --local ceph_service.list
salt-call --local ceph_service.get rgw.realm.zone
salt-call --local ceph_service.daemons rgw.realm.zone
```

`list` uses API version `2.0`, including Dashboard pagination and the
`X-Total-Count` response header. Its default `limit=-1` deliberately returns the
complete service set for inventory and IaC consumers; pass `offset` and `limit`
to page a large result. Supported sort fields are `service_name`,
`status.running`, `status.last_refreshed`, and `status.size`, optionally prefixed
with `+` or `-`. All other service endpoints use API version `1.0`.

Create and update accept `service_spec` as a mapping, never as a pre-serialized
JSON or YAML string:

```bash
salt-call --local ceph_service.create rgw.realm.zone \
  service_spec='{"service_type":"rgw","service_id":"realm.zone","placement":{"label":"rgw"}}'

salt-call --local ceph_service.update rgw.realm.zone \
  service_spec='{"service_type":"rgw","service_id":"realm.zone","placement":{"count":3,"label":"rgw"}}'
```

Nested placement, network, config, custom configuration, container argument, and
service-specific data pass through as JSON-compatible structures. The client
checks that the route name matches `service_type` plus optional `service_id`.
Specs exported by Ceph that identify themselves with `service_name` are also
accepted. Ceph itself performs the release-specific ServiceSpec validation.

Dashboard create calls the orchestrator with `no_overwrite=True`; it fails if a
service already exists. Update applies the supplied spec with overwrite enabled.
Cephadm then continually reconciles deployed daemons against that whole spec, so
an incomplete update can change placement or remove daemons. Read the current
spec, edit it, and submit the complete intended document.

```bash
salt-call --local ceph_service.delete rgw.realm.zone confirm=true
```

Deleting a service asks the orchestrator to remove the service and its daemons
and requires `confirm=true`.
Create, update, and delete are Dashboard tasks and can return `202`; the common
response envelope reports acceptance and does not imply convergence. Daemon
status also comes from the orchestrator cache and can lag the hosts.

The local Dashboard OpenAPI document describes `service_spec` as a string, but
the controller calls `ServiceSpec.from_json()` with a dictionary and the
Dashboard frontend sends an object. This extension follows the controller
contract.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/service.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/service.py),
and the [Ceph service management documentation](https://docs.ceph.com/en/reef/cephadm/services/).
