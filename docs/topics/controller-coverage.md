# Ceph Dashboard controller coverage

The execution layer is organized by the public, versioned `/api` controllers in
Ceph rather than by Dashboard screens. This inventory makes omissions reviewable
when upstream adds or changes a controller. A mapped controller can expose more
than one Salt module when its resource families have different contracts.

## Public controllers

| Ceph controller source | Salt execution module |
| --- | --- |
| `auth.py` | `ceph_auth` |
| `ceph_users.py` | `ceph_users` |
| `cephfs.py` | `cephfs` |
| `certificate.py` | `ceph_certificates` (current-only) |
| `cluster.py` | `ceph_cluster` |
| `cluster_configuration.py` | `ceph_cluster_config` |
| `crush_rule.py` | `ceph_crush_rule` |
| `daemon.py` | `ceph_daemon` |
| `erasure_code_profile.py` | `ceph_erasure_code_profile` |
| `grafana.py` | `ceph_grafana` |
| `hardware.py` | `ceph_hardware` (current-only) |
| `health.py` | `ceph_health` |
| `host.py` | `ceph_host` |
| `iscsi.py` | `ceph_iscsi` |
| `logs.py` | `ceph_logs` |
| `mgr_modules.py` | `ceph_mgr_module` |
| `monitor.py` | `ceph_monitor` |
| `multi_cluster.py` | `ceph_multi_cluster` (current-only) |
| `nfs.py` | `ceph_nfs` |
| `nvmeof.py` | `ceph_nvmeof` (current-only) |
| `osd.py` | `ceph_osd` |
| `perf_counters.py` | `ceph_perf_counter` |
| `pool.py` | `ceph_pool` |
| `prometheus.py` | `ceph_prometheus` |
| `rbd.py` | `ceph_rbd`; `ceph_rbd_group` is current-only |
| `rbd_mirroring.py` | `ceph_rbd_mirroring` |
| `rgw.py` | `ceph_rgw_daemon`, `ceph_rgw_bucket`, `ceph_rgw_user`, `ceph_rgw_multisite`, and `ceph_rgw_iam`; `ceph_rgw_topic` is current-only |
| `rgw_iam.py` | Current-only account and quota operations in `ceph_rgw_iam` |
| `role.py` | `ceph_role` |
| `service.py` | `ceph_service` |
| `settings.py` | `ceph_settings` |
| `smb.py` | `ceph_smb` (current-only) |
| `summary.py` | `ceph_summary` |
| `task.py` | `ceph_task` |
| `telemetry.py` | `ceph_telemetry` |
| `user.py` | `ceph_dashboard_user` |

Each typed execution module has a salt-ssh wrapper with the same public function
names and signatures. A structural test enforces this parity. Endpoint-specific
tests also check API versions, path encoding, request shapes, response validation,
secret redaction, and destructive confirmations.

Some controllers present in both source trees gained individual routes after
Reef. Their resource guides identify those operation-level boundaries; a row is
marked current-only above only when the whole controller or Salt resource family
is absent from Reef.

## Public controllers registered by plugins

Dashboard plugins can register routes outside the main controller directory.
They are part of the same inventory:

| Ceph plugin source | Salt execution module |
| --- | --- |
| `plugins/feature_toggles.py` | `ceph_feature_toggles` (read-only) |
| `plugins/motd.py` | `ceph_motd` (current-only create/clear) |

Feature enable/disable operations are Ceph manager CLI commands and have no HTTP
route. The MOTD read route remains private `/ui-api`, so its public mutations
cannot support a truthful declarative state. The `debug.py` plugin changes server
behavior but registers no API controller; the remaining plugin files provide
framework infrastructure rather than cluster-resource endpoints.

## Reviewed exclusions

| Ceph controller source | Reason |
| --- | --- |
| `docs.py` | Serves generated API documentation rather than a cluster resource. |
| `feedback.py` | Sends data and a stored tracker credential to an external issue tracker. |
| `frontend_logging.py` | Receives browser log records; it is an inbound callback. |
| `home.py` | Serves the Dashboard frontend and static metadata. |
| `oauth2.py` | Implements an interactive browser login/redirect flow. |
| `orchestrator.py` | Contains Dashboard UI helpers and capability aggregation, not a versioned public resource controller. |
| `saml2.py` | Implements an interactive browser SSO flow. |

Private `UIRouter` routes are excluded even when they live beside a public
`APIRouter`. Methods exposed only as manager CLI commands are also excluded:
inventing HTTP paths for them would create an interface Ceph does not provide.
Transport internals and controller framework files whose names begin with `_`
are implementation machinery rather than API resources.

Compare this inventory with the
[current controller tree](https://github.com/ceph/ceph/tree/main/src/pybind/mgr/dashboard/controllers),
the [Reef controller tree](https://github.com/ceph/ceph/tree/reef/src/pybind/mgr/dashboard/controllers),
and Ceph's [versioned REST API documentation](https://docs.ceph.com/en/latest/mgr/ceph_api/)
when adding a release target. The generated OpenAPI file is a secondary source;
controller decorators and upstream tests determine whether a route is public.

The last complete route audit used Ceph main commit
`cb76fd5ba4263a0f64e2e9feb8f34f8a9e495538` and Reef commit
`0f9a110bf1d461934e3bc579503a9de9d91d9b0e`. After the exclusions above, all
429 main operations and all 273 Reef operations had an implementation. The
local development `openapi.json` snapshot contained 314 older operations, so it
must not be used as the sole compatibility inventory.
