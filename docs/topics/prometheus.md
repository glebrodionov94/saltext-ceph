# Prometheus and Alertmanager

`ceph_prometheus` uses the Dashboard proxy endpoints, so the control node needs
network access only to Dashboard. Dashboard itself connects to Prometheus and
Alertmanager using its configured monitoring stack.

```console
salt-call --local ceph_prometheus.alerts cluster_filter=true
salt-call --local ceph_prometheus.rules
salt-call --local ceph_prometheus.query_range \
  'rate(ceph_osd_op_w[5m])' start=1720000000 end=1720003600 step=15
salt-call --local ceph_prometheus.silences
salt-call --local ceph_prometheus.notifications from_=last
```

Silences are operational, time-bound objects rather than desired cluster
configuration. Create them from a JSON mapping and delete them explicitly:

```console
salt-call --local ceph_prometheus.create_silence \
  silence='{"matchers":[],"startsAt":"...","endsAt":"...",\
"createdBy":"automation","comment":"maintenance"}'
salt-call --local ceph_prometheus.delete_silence SILENCE_ID confirm=true
```

Current Ceph also provides instant query, alert-group, and remote-write routes:

```console
salt-call --local ceph_prometheus.query up
salt-call --local ceph_prometheus.alert_groups cluster_filter=true
salt-call --local ceph_prometheus.set_remote_write \
  https://metrics.example/api/v1/write \
  allowed_metrics='[ceph_health_status,ceph_osd_op]'
salt-call --local ceph_prometheus.remove_remote_write \
  https://metrics.example/api/v1/write confirm=true
```

Those four operations are absent from Reef 18.2.8. Remote-write is intentionally
an execution operation rather than a state: the public controller has set/remove
methods but no read method that can verify the current configuration. The client
rejects credentials and query strings in remote-write URLs so secrets do not
enter Salt job arguments.

The implementation follows the official
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/prometheus.py)
and compares it with the
[Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/prometheus.py).
