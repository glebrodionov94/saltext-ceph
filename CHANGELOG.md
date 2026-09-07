The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

This project uses [Semantic Versioning](https://semver.org/) - MAJOR.MINOR.PATCH

# Changelog

## 0.1.0 (2026-09-07)


### Changed

- Hardened the release pipeline around tokenless PyPI Trusted Publishing, protected
  GitHub environments, package archive validation, and least-privilege workflow
  permissions.
- Require an explicit real boolean confirmation for permanent deletion of CephX
  users, pools, cephadm services and hosts, CRUSH rules, erasure-code profiles,
  Dashboard users, and Dashboard roles across raw, execution, wrapper, and state
  interfaces. Low-level mutating ``ceph.query`` calls now require the same explicit
  confirmation and remain unavailable in Salt test mode.
- Require explicit confirmation for destructive CephFS execution operations,
  including removals, path replacement, client eviction, retention removal, and
  snapshot-mirroring teardown.
- ﻿Publish installation instructions and package metadata for the first PyPI and GitHub Pages release.


### Fixed

- Accept the Dashboard ``Off`` versioning status for newly created RGW buckets so dry-runs and convergence can enable versioning across Reef and newer Ceph releases.
- Authentication check and logout requests now send an empty JSON object so Ceph
  Tentacle accepts their POST media type.
- Avoid querying RGW Admin Ops through a removed daemon after the destructive lifecycle has already confirmed bucket, user, and service absence.
- Confirm OSD removal from Dashboard's raw OSD map, tolerating broken removal-task and detailed-list responses while recognizing preserved ``destroyed`` IDs.
- Correct the RGW IAM controller inventory, Prometheus route count, and iSCSI SLS highlighting.
- Document that package builds and metadata checks must use the isolated, pinned
  release tool set instead of the Salt runtime environment.
- Normalize Dashboard's XML-derived bucket lifecycle response before state comparison, including Rule/Rules shape and numeric duration fields.
- Poll Dashboard after pool mutations and reconcile one mutable post-create drift so eventually consistent create, update, and delete operations converge within the state's declared task timeout.
- Preserve shell line continuations in generated execution-module examples.
- Reject unsupported tenant-user creation before the Ceph Dashboard endpoint returns an opaque HTTP 500, while preserving tenant-aware reads and existing-user reconciliation.
- Remove an unused changed-file filter that referred to an obsolete test-release path.
- Use the full RGW subuser identity for permission updates and deletion so Dashboard selects its update branch without rotating credentials.
- Validate the Sphinx Python coverage report from its real output directory and deploy release documentation only after a successful, same-repository release workflow.
- Wait for cephadm to remove the filesystem's MDS daemons before reporting CephFS deletion as converged.


### Added

- Add Dashboard asynchronous task inspection and bounded, failure-aware polling,
  with safe output defaults and an explicit diagnostic opt-in for raw task details.
- Add Dashboard login-user management and file-based password operations with
  defensive secret redaction.
- Add Dashboard login-user states with public-field projection, create-only
  file-sourced passwords, post-write verification, and confirmed deletion.
- Add Dashboard role list, get, create, update, delete, and clone operations.
- Add Dashboard settings management with file-based secret input and redacted
  credential values.
- Add OSD device-class, cluster flag, individual flag, and guarded removal states.
- Add OSD inventory, diagnostics, safety checks, guarded lifecycle actions, and flag management through the Dashboard API.
- Add RBD image, namespace, snapshot, trash, copy, clone, configuration, metadata,
  and mirroring-schedule execution and salt-ssh operations with API v2 pagination
  and confirmation guards for destructive changes.
- Add RBD mirroring summaries, site and pool modes, protected bootstrap-token files,
  legacy peer management with key redaction, and current-main image status support.
- Add RGW user, capability, key, quota, subuser, and rate-limit operations with file-sourced credentials and secret redaction.
- Add Reef global roles and current account-scoped RGW account, role, and quota operations.
- Add ``ceph_auth`` execution and salt-ssh wrapper modules for safe Dashboard
  login, token validation and logout without returning JWTs.
- Add ``ceph_users`` execution and salt-ssh wrapper modules for CephX user and
  capability management, with file-based keyring import and export.
  Permanent deletion requires an explicit boolean confirmation.
- Add a shared Ceph Dashboard HTTP client with validated connection profiles, JWT
  authentication, in-memory sessions and explicit per-operation API versions.
  Add salt-ssh query and local cache management wrappers, protocol tests and usage documentation.
- Add all 48 current public Ceph Dashboard NVMe-oF gateway, SPDK, subsystem,
  listener, namespace, host, and connection endpoints with salt-ssh parity,
  file-only authentication secrets, response redaction, validation, and explicit
  confirmation guards for destructive or disruptive operations.
- Add an idempotent telemetry opt-in state backed by the persisted manager-module
  enablement flag and guarded by explicit license acceptance.
- Add current Ceph RGW notification topic CRUD with file-sourced endpoint data and credential redaction.
- Add current-Ceph RBD group and crash-consistent group-snapshot execution and
  salt-ssh operations.
- Add current-Ceph RBD group, exact membership, and group-snapshot existence
  states with test mode, task waits, verification, and destructive guards.
- Add current-only declarative NVMe-oF gateway configuration, subsystem, listener,
  host, and namespace states with exact GET projections, asynchronous task waits,
  post-mutation verification, secret-source handling, test mode, and explicit
  destructive confirmation guards.
- Add current-only, secret-safe Dashboard multi-cluster connection management with
  an explicit TLS-verification policy, file-based credentials, redacted reads, URL
  validation, and guarded deletion.
- Add current-release hardware health inspection through Ceph Dashboard.
- Add declarative CephFS states for filesystems, directories, snapshots,
  subvolumes, groups, snapshot schedules, and snapshot-mirroring peers and paths.
- Add declarative RBD image, namespace, and snapshot states with exact observable
  projections, test mode, asynchronous task waits, post-read verification, and
  confirmation guards for destructive changes.
- Add declarative RBD mirroring site, pool-mode, and legacy-peer states with
  create-only file-sourced peer keys and secret-free state changes.
- Add declarative RGW user, bucket, multisite, topic, account, role, quota, rate-limit, placement, and sync-policy states with test mode, task waiting, post-read verification, destructive guards, and a secret-safe changes boundary.
- Add declarative manager module enablement and secret-redacted option reconciliation.
- Add exact ServiceSpec presence and guarded service deletion states with task completion checks.
- Add execution and salt-ssh wrapper modules for Ceph cluster health views.
- Add execution and salt-ssh wrapper modules for Ceph erasure-code profiles.
- Add execution and salt-ssh wrapper modules for public RADOS pool CRUD, statistics, and RBD configuration operations.
- Add execution and salt-ssh wrapper modules for public cephadm service CRUD, inventory, and daemon operations.
- Add execution and salt-ssh wrapper modules for the Ceph Dashboard Grafana integration.
- Add fail-closed, opt-in live acceptance lifecycles for cephadm hosts and
  services, exact-device OSD provisioning, RBD, CephFS, and RGW resources.
- Add guarded RGW bucket CRUD, encryption, lifecycle, notification, and rate-limit operations with file-sourced KMS and MFA secrets.
- Add guarded RGW realm, zonegroup, zone, storage-class, and sync-policy operations with file-sourced credentials.
- Add guarded current-Ceph operations for setting and clearing the public
  Dashboard message-of-the-day endpoint.
- Add host CRUD, lifecycle actions, inventory, and diagnostics for the cephadm orchestrator.
- Add host presence, label, maintenance, and guarded deletion reconciliation states.
- Add idempotent Dashboard role states with exact permission reconciliation,
  built-in role protection, asynchronous task waiting, and confirmed deletion.
- Add idempotent present and absent states for CephX entities and capabilities.
- Add immutable-aware presence, explicit replacement, and guarded deletion states for CRUSH rules and erasure-code profiles.
- Add manager module enablement and persistent option operations.
- Add opt-in live Dashboard state tests for test-mode plans and exact-resource
  role and login-user CRUD reconciliation with FSID and confirmation safeguards.
- Add opt-in read-only live Dashboard smoke tests for TLS, authentication, health,
  and cluster identity validation.
- Add partial or exact declarative reconciliation and section removal states for Ceph configuration.
- Add pool creation, mutable property reconciliation, immutable drift detection, and guarded deletion states.
- Add public NFS cluster inventory and guarded NFS export CRUD through API versions 0.1, 1.0, and 2.0.
- Add public RGW daemon inventory, detail, site discovery, and Dashboard multisite selection.
- Add public iSCSI discovery authentication and guarded structured target management through Dashboard API version 1.0.
  CHAP secrets are recursively redacted from API returns by default.
- Add read-only inspection of the public Dashboard feature-toggle endpoint that is
  registered by the Ceph manager plugin outside the main controller directory.
- Add read-only, transition-aware Salt beacons for Ceph cluster health, completed
  Dashboard tasks, and cephadm certificate expiry without exposing secret-bearing
  API fields.
- Add shared read-diff-test-write-task-wait helpers for declarative Ceph states.
- Add telemetry report preview and explicit-license enable or disable operations.
- Add the ``cephfs`` execution and salt-ssh wrapper modules for filesystems,
  clients, namespace operations, subvolumes, groups, snapshots, schedules, and
  current-release snapshot mirroring.
- Add the read-only ``ceph_certificates`` execution and salt-ssh wrapper modules for
  cephadm certificate inventory, service certificate status, and the public root CA.
- Add type-exact Dashboard setting management and confirmed reset states that fail
  safely when redaction prevents a truthful drift comparison.
- Added CRUSH rule execution modules for replicated and current-Ceph erasure rules.
- Added Prometheus and Alertmanager query, silence, notification, and current-release remote-write operations.
- Added cephadm daemon inventory and lifecycle action execution modules.
- Added cluster configuration execution modules with per-section set, remove, filter, and bulk operations.
- Added cluster status and cephadm upgrade execution modules with salt-ssh support.
- Added current-Ceph SMB cluster, share, join-auth, users/groups, and share QoS operations with file-based secrets and redacted returns.
- Added declarative NFS export reconciliation keyed by cluster and pseudo path.
- Added declarative current-Ceph SMB cluster, share, and share-QoS states.
- Added direct Ceph task inspection and exact-target, FSID-verified GitOps plan/apply runners.
- Added full-configuration iSCSI target states with guarded replacement, guarded deletion, task waits, and redacted changes.
- Added read-only modules for Dashboard logs, monitor quorum, aggregate summary, and daemon performance counters.
- An explicitly gated live-cluster suite now validates typed API adapters, real
  Salt execution-module loading, reversible state lifecycles, and destructive
  resource allowlists without storing credentials in the repository.
- Connection profiles can read Dashboard passwords and tokens from absolute,
  non-symlink files, keeping credential values out of Git-managed Salt data.
- Document least-privilege Ceph Dashboard scopes for each Salt resource family and
  the CLI bootstrap flow for a dedicated automation identity.
- Document the mapping from Ceph Dashboard public controller sources to Salt
  execution modules, including reviewed exclusions and compatibility boundaries.
- Initialize the Ceph REST API extension scaffold with packaging, Salt loader
  registration, test fixtures, documentation, and CI.


### Security

- Add a pre-commit credential scanner that detects common long-lived PyPI,
  GitHub, and AWS tokens and private-key headers without printing matched values.
  Route vulnerability reports to this repository's private GitHub Security
  Advisories instead of the upstream Salt security address.
- Prevent the GitOps runner from returning state-job arguments, reject malformed
  beacon API envelopes, and bound beacon configuration and task fingerprint work.
- Reject a percent-encoded `/api` suffix in Dashboard root URLs before attaching credentials.
