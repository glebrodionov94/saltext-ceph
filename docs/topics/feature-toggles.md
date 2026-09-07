# Dashboard feature toggles

The read-only `ceph_feature_toggles` execution module reports which optional
Dashboard controller families are enabled:

```bash
salt-call --local ceph_feature_toggles.list
```

The result is a mapping from feature name to boolean status. Reef also reports
the historical `dashboard` entry, while current Ceph reports the controller
families it can filter. The adapter accepts both shapes and preserves new boolean
features so it remains useful when Ceph adds another toggle.

Dashboard registers this public route from a plugin rather than from the main
`controllers` directory. Enabling and disabling features remains a Ceph manager
CLI operation; Dashboard exposes no HTTP mutation route, so this extension does
not invent one or model feature status as a Salt state.

The implementation follows the version `1.0` endpoint in the
[current feature-toggles plugin](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/plugins/feature_toggles.py)
and its [Reef version](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/plugins/feature_toggles.py).
