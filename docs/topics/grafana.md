# Grafana integration

The `ceph_grafana` execution module operates Ceph Dashboard's public
`/api/grafana` endpoints.

```bash
salt-call --local ceph_grafana.url
salt-call --local ceph_grafana.validate_dashboard ceph-cluster
salt-call --local ceph_grafana.push_dashboards
```

`url` returns the frontend Grafana instance selected by Ceph Dashboard.
`validate_dashboard` asks the active manager to request
`/api/dashboards/uid/<uid>` from its configured Grafana instance and returns the
resulting Grafana HTTP status code.

`push_dashboards` reads the bundled dashboards on the active manager and uploads
them to Grafana with overwrite enabled. It is an explicit action because this API
does not expose Grafana dashboard content for comparison. Use it from an
orchestrated Salt run or an `onchanges` requisite instead of treating every call
as a declarative change.

The Grafana URL, credentials, and TLS verification are Dashboard settings. They
will be managed through the separate `settings.py` controller; this module does
not accept or return those credentials.

All operations use Dashboard API version `1.0` and return the common `status`,
`data`, and `headers` envelope.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/grafana.py),
the [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/grafana.py),
and the [upstream controller tests](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/tests/test_grafana.py).
