# Hardware health

The `ceph_hardware` execution module reads the hardware health summary collected
by the cephadm orchestrator.

```bash
salt-call --local ceph_hardware.summary
salt-call --local ceph_hardware.summary \
  categories='["storage","memory"]' hostnames='["node1","node2"]'
```

Supported categories are `memory`, `storage`, `processors`, `network`, `power`,
`fans`, and `temperatures`. Omitting filters requests every category and host.
The operation uses experimental Dashboard API version `0.1` and is available in
current Ceph releases; Ceph Reef does not contain this controller.

The module is read-only and returns the common `status`, `data`, and `headers`
envelope. Its summary is suitable as an input to a Salt beacon because the
orchestrator already consolidates health states by component and host.

The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/hardware.py)
and [hardware service tests](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/tests/test_hardware.py).
