# Manager modules

The `ceph_mgr_module` execution module manages Ceph manager module enablement and
persistent module options.

```bash
salt-call --local ceph_mgr_module.list
salt-call --local ceph_mgr_module.get_config prometheus
salt-call --local ceph_mgr_module.options prometheus
salt-call --local ceph_mgr_module.set_config prometheus \
  config='{"server_port":9283}'
salt-call --local ceph_mgr_module.enable prometheus
salt-call --local ceph_mgr_module.disable prometheus
```

`get_config` returns effective stored values, while `options` returns type,
default, range, enum, and description metadata. `set_config` updates only keys
present in the supplied mapping; JSON `null` can be passed to options whose Ceph
implementation supports resetting them.

The optional `force=true` enable flag is available on current Ceph. It is omitted
by default so the same call works with Reef. Always-on modules are reported by
`list` and cannot be disabled by a state. The Dashboard intentionally excludes
its `selftest` module.

Module options may contain credentials or endpoints. Salt returners and job cache
permissions must be configured accordingly; declarative states redact values in
their change report when an option is marked secret in pillar.

All endpoints use Dashboard API version `1.0`. The implementation follows the
[current controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/mgr_modules.py)
and [Reef controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/mgr_modules.py).
