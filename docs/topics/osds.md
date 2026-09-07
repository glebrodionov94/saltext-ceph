# OSDs

The `ceph_osd` execution module exposes Dashboard's public OSD controllers for
inventory, diagnostics, operational actions, safety checks, and flags.

```bash
salt-call --local ceph_osd.list
salt-call --local ceph_osd.get 7
salt-call --local ceph_osd.devices 7
salt-call --local ceph_osd.smart 7
salt-call --local ceph_osd.histogram 7
salt-call --local ceph_osd.settings
salt-call --local ceph_osd.safe_to_destroy '[7,8]'
salt-call --local ceph_osd.safe_to_delete '[7,8]'
```

The list call requests all OSDs by default (`limit=-1`) and retains the
`X-Total-Count` response header. It uses API version `1.1`; the fullness settings
endpoint uses experimental `0.1`; all other calls use `1.0`.

Operational changes are explicit:

```bash
salt-call --local ceph_osd.set_device_class 7 nvme
salt-call --local ceph_osd.scrub 7 deep=true
salt-call --local ceph_osd.mark 7 out
salt-call --local ceph_osd.reweight 7 0.8
salt-call --local ceph_osd.set_individual_flags \
  flags='{"noout":true}' ids='[7,8]'
```

`reweight` is temporary Ceph runtime state. OSD provisioning should normally be
declared as an `osd` service specification through `ceph_service`; the raw
`create` call remains available for controller parity and recovery workflows.

Creating or irreversibly changing OSDs requires `confirm=true`. This applies to
`create`, `remove`, `purge`, `destroy`, and the `lost` mark action. `remove`
always sends `force=false` unless explicitly overridden. This matters because
Dashboard only performs its OSD fullness health check when the `force` query
parameter is present and false.

```bash
salt-call --local ceph_osd.remove 7 confirm=true
salt-call --local ceph_osd.remove 7 preserve_id=true confirm=true
salt-call --local ceph_osd.purge 7 confirm=true
salt-call --local ceph_osd.destroy 7 confirm=true
salt-call --local ceph_osd.mark 7 lost confirm=true
```

Cluster-wide flags are a complete replacement API. Read the current list before
calling `set_flags`, retain Ceph's non-removable flags, and use the OSD flag state
for GitOps reconciliation. Individual updates accept only `noin`, `noout`,
`noup`, and `nodown`, with `null` meaning no change.

The implementation follows the [current OSD controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/osd.py),
the [Reef OSD controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/osd.py),
and [Ceph OSD service documentation](https://docs.ceph.com/en/latest/cephadm/services/osd/).
