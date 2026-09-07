# Scope and compatibility

`saltext.ceph` manages Ceph through the public Dashboard `/api` controllers.
The extension does not replace cephadm: cephadm remains the orchestrator that
reconciles hosts, service specifications, and daemons. Salt supplies connection
profiles, validates desired data, calls that API, waits for Dashboard tasks, and
checks the resulting resource again.

The extension does not bootstrap Ceph packages, install Podman, prepare disks, or
configure host networking. Those host-local prerequisites belong to cephadm and
the surrounding OS formula. Once Dashboard is reachable, this extension manages
the API-visible cluster state.

## Compatibility policy

Ceph Dashboard describes its REST API as still evolving. Every adapter therefore
declares the exact API media version used by its controller instead of assuming
one global version. The implementation is source-checked against Ceph Reef
(`18.2`) and current upstream. A guide labels an operation **current-only** when
the public route does not exist in Reef. Such an operation fails with Ceph's
normal HTTP error on an older cluster; it is never silently translated into a
different command.

The generated `openapi.json` captured from a real cluster is a development
reference. It is ignored by Git and excluded from distributions. Controller
source and controller tests take precedence where generated parameter types are
incomplete.

The opt-in acceptance suite has also run against Ceph 20.2.4 Tentacle. It
validated authentication, core and cephadm read paths, Salt execution-module
loading, and reversible Dashboard role/user states. Reef remains source-checked;
it has not yet been exercised by this live test environment. See [Live cluster
testing](live-testing.md) for the exact tiers and recorded cluster limitations.

The package requires Python 3.10 or newer and Salt 3006 or newer. CI tests the
declared platform combinations in `.github/workflows/test-action.yml`, currently
including Salt 3006.27 and 3008.2 on Linux, Windows, and macOS. A lower-bound
dependency is not a claim that every future Salt release is already validated;
add a new CI target before relying on one in production.

## Supported controller families

| Area | Execution and salt-ssh interface | Declarative interface |
| --- | --- | --- |
| Authentication and session lifecycle | `ceph_auth` | Connection profile |
| Dashboard feature availability | `ceph_feature_toggles` | Read-only; enable/disable is CLI-only |
| Current Dashboard message of the day | `ceph_motd` | Operational calls only; public read is unavailable |
| CephX identities and capabilities | `ceph_users` | `ceph_users.present`, `absent` |
| Cluster status and cephadm upgrades | `ceph_cluster` | Operational calls only |
| Monitor configuration database | `ceph_cluster_config` | `managed`, `absent` |
| Orchestrator hosts and labels | `ceph_host` | `present`, `absent` |
| cephadm service specifications | `ceph_service` | `present`, `absent` |
| Daemon inventory and lifecycle actions | `ceph_daemon` | Operational calls only |
| OSD inventory, flags, device classes, removal | `ceph_osd` | Flag/device-class management and `absent` |
| Pools, CRUSH rules, erasure profiles | `ceph_pool`, `ceph_crush_rule`, `ceph_erasure_code_profile` | `present`, `absent` |
| CephFS, subvolumes, snapshots, schedules, mirroring | `cephfs` | Resource states are documented in the CephFS guide |
| RBD images, snapshots, namespaces, groups, mirroring | `ceph_rbd*` | Resource states are documented in the RBD guides |
| NFS exports | `ceph_nfs` | `present`, `absent` |
| iSCSI targets | `ceph_iscsi` | `present`, `absent` |
| SMB clusters and shares | `ceph_smb` | Cluster/share lifecycle and share QoS |
| RGW daemons, users, buckets, topics, multisite and IAM | `ceph_rgw_*` | Only resources with a stable, readable desired-state projection |
| Current NVMe-oF gateways, subsystems, listeners, hosts and namespaces | `ceph_nvmeof` | Only resources with a stable, readable desired-state projection |
| Dashboard users, roles and settings | `ceph_dashboard_user`, `ceph_role`, `ceph_settings` | User/role lifecycle and non-secret settings |
| Current Dashboard multi-cluster hub | `ceph_multi_cluster` | No stable credential-free state projection |
| Manager modules and telemetry | `ceph_mgr_module`, `ceph_telemetry` | `managed` |
| Current certificates, health, and current hardware | `ceph_certificates`, `ceph_health`, `ceph_hardware` | Read-only; beacons emit meaningful changes |
| Logs, monitors, counters and summary | `ceph_logs`, `ceph_monitor`, `ceph_perf_counter`, `ceph_summary` | Read-only |
| Prometheus proxy, alerts and silences | `ceph_prometheus` | Operational calls only |
| Grafana integration | `ceph_grafana` | Inspection and explicit dashboard push |
| Dashboard asynchronous tasks | `ceph_task` | Shared task wait used by states |

Execution functions expose imperative API operations. A state exists only when
Dashboard exposes enough readable data to calculate drift and verify convergence.
One-shot actions such as daemon restart, upgrade control, snapshot rollback,
task cancellation, alert silencing, and dashboard upload deliberately remain
execution functions. Modeling them as continuously desired resources would cause
Salt to repeat an operation during later highstates.

## Deliberate exclusions

- `/ui-api` controllers and UI aggregation methods are private frontend
  implementation details rather than the versioned public API contract.
- OAuth2 and SAML browser redirects are interactive login flows. API automation
  uses the local Dashboard token or username/password authentication controller.
- `prometheus_receiver` and frontend logging accept inbound data from other
  components; they are server callbacks, not Ceph resources for Salt to manage.
- The feedback controller sends reports to an external issue tracker and stores
  its API key. It is outside cluster IaC and is not exposed by this extension.
- Controller helper classes, generated API documentation, home pages, language
  lists, and static assets do not represent manageable cluster resources.
- Methods decorated only as Ceph manager CLI commands have no Dashboard HTTP
  route and cannot be implemented by an HTTP-only extension.

Each resource guide records narrower release boundaries and known API limits.
Run the opt-in live smoke tests against every target Ceph release before enabling
mutating GitOps pipelines.

The [controller coverage inventory](controller-coverage.md) maps every reviewed
public source controller to its execution module and records the excluded files.

References: [Ceph Dashboard API](https://docs.ceph.com/en/reef/mgr/ceph_api/),
[cephadm services](https://docs.ceph.com/en/reef/cephadm/services/), and the
[Dashboard controllers](https://github.com/ceph/ceph/tree/main/src/pybind/mgr/dashboard/controllers).
