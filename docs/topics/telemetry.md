# Telemetry

The `ceph_telemetry` execution module previews the report assembled by Ceph's
telemetry manager module and controls periodic submission through Dashboard.

## Preview the report

```bash
salt-call --local ceph_telemetry.report
```

The result includes Ceph's `report` and `device_report` mappings in the
common `status`, `data`, and `headers` envelope. Generating a report can take time
on large clusters. Ceph documents the fields and privacy model in the
[Telemetry module guide](https://docs.ceph.com/en/reef/mgr/telemetry/). Review the
preview before opting in; device data is generated separately and anonymized by
Ceph.

## Enable or disable submission

```bash
salt-call --local ceph_telemetry.set true license_name=sharing-1-0
salt-call --local ceph_telemetry.set false
```

Enabling requires the exact `sharing-1-0` value, recording explicit acceptance of
the Community Data License Agreement - Sharing - Version 1.0. Disabling omits the
license field. The response reports the requested boolean state and HTTP metadata.
This endpoint controls the telemetry module's on/off state; channel selection,
contact information, proxy configuration, and reporting interval remain telemetry
manager-module settings.

## Declarative state

The `ceph_telemetry.managed` state reads the telemetry manager module's persisted
`enabled` option, changes it only when needed, and verifies it after the mutation.
The report endpoint itself is only a preview and does not expose opt-in status.

```yaml
ceph-telemetry-opt-in:
  ceph_telemetry.managed:
    - enabled: true
    - license_name: sharing-1-0

ceph-telemetry-opt-out:
  ceph_telemetry.managed:
    - enabled: false
```

Every declaration that enables submission must contain the exact
`sharing-1-0` license value, including no-op runs. It is an explicit consent
guard and does not appear in the state diff. Test mode, HTTP 202 task waiting,
and post-write verification are supported.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/telemetry.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/telemetry.py),
and the [Dashboard frontend client](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/frontend/src/app/shared/api/telemetry.service.ts).
Both releases expose `GET /api/telemetry/report` and `PUT /api/telemetry` using API
version `1.0`. The local OpenAPI describes `device_report` as a string, while the
telemetry manager module returns the mapping produced by `gather_device_report`.
