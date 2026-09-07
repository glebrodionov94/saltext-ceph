# NVMe over Fabrics

The `ceph_nvmeof` execution module exposes the 48 versioned public endpoints in
the current Ceph Dashboard `nvmeof.py` controller. Every request uses Dashboard
API version `1.0`. This surface targets current Ceph main. The Reef branch has no
`controllers/nvmeof.py`, so all 48 operations are main-only relative to Reef.

Pass NQNs and addresses in decoded form. The extension validates and encodes
each URL segment, accepts namespace IDs as positive integers or decimal strings,
normalizes UUIDs, IP addresses and CIDR networks, and rejects ambiguous use of
`server_address` with the deprecated routing argument `traddr`.

## Gateways and SPDK logging

Gateway information, groups, versions, logging, IO statistics, thread statistics,
listener inspection, and network refresh are available as follows:

```bash
salt-call --local ceph_nvmeof.gateway_info gw_group=alpha
salt-call --local ceph_nvmeof.gateway_groups
salt-call --local ceph_nvmeof.gateway_version server_address=gw1.example
salt-call --local ceph_nvmeof.gateway_log_level gw_group=alpha
salt-call --local ceph_nvmeof.gateway_set_log_level warning gw_group=alpha
salt-call --local ceph_nvmeof.gateway_stats gw_group=alpha
salt-call --local ceph_nvmeof.gateway_listener_info \
  nqn.2026-09.io.example:storage gw_group=alpha
salt-call --local ceph_nvmeof.gateway_set_io_stats true gw_group=alpha
salt-call --local ceph_nvmeof.gateway_thread_stats gw_group=alpha
salt-call --local ceph_nvmeof.gateway_refresh_network \
  server_address=gw1.example confirm=true

salt-call --local ceph_nvmeof.spdk_log_level all_log_flags=true
salt-call --local ceph_nvmeof.spdk_set_log_level \
  log_level=INFO print_level=NOTICE extra_log_flags='["nvmf"]'
salt-call --local ceph_nvmeof.spdk_disable_log_level \
  extra_log_flags='["nvmf"]'
```

`gateway_refresh_network` may add and remove automatically managed listeners, so
it requires `confirm=true` and an explicit `server_address` or legacy `traddr`.
The two routing arguments are gateway selectors here; a listener's transport
address is independently named `traddr` by the listener API.

## Subsystems, listeners, hosts, and connections

Subsystem operations are `subsystem_list`, `subsystem_get`,
`subsystem_create`, `subsystem_delete`, and `subsystem_change_key`. Creation can
configure automatic listener networks, their port and secure mode, serial and
model fields, maximum namespaces, and an optional in-band DHCHAP key.

```bash
salt-call --local ceph_nvmeof.subsystem_create \
  nqn.2026-09.io.example:storage \
  max_namespaces=128 network_mask='["192.0.2.0/24"]' port=4420
salt-call --local ceph_nvmeof.subsystem_delete \
  nqn.2026-09.io.example:storage confirm=true

salt-call --local ceph_nvmeof.listener_create \
  nqn.2026-09.io.example:storage gw1 192.0.2.10 trsvcid=4420
salt-call --local ceph_nvmeof.listener_list nqn.2026-09.io.example:storage
salt-call --local ceph_nvmeof.listener_delete \
  nqn.2026-09.io.example:storage gw1 192.0.2.10 4420 confirm=true
```

Host operations are `host_list`, `host_create`, `host_delete`,
`host_change_key`, `host_change_controller_key`, `host_delete_key`, and
`host_delete_controller_key`. A literal `*` host enables open subsystem access;
authentication material cannot accompany that wildcard. `connection_list`
returns the active connections for a subsystem.

Subsystem, listener, host, namespace, and key deletion requires exact boolean
confirmation. Forced listener creation, forced namespace creation, forced host
grants, and forced QoS changes also require confirmation. Key rotations require
confirmation because a mismatched initiator loses access.

## Secret files

DHCHAP and TLS-PSK values are only accepted through absolute source files:

```bash
salt-call --local ceph_nvmeof.subsystem_create \
  nqn.2026-09.io.example:storage \
  dhchap_key_source=/run/secrets/subsystem-dhchap
salt-call --local ceph_nvmeof.subsystem_change_key \
  nqn.2026-09.io.example:storage /run/secrets/subsystem-dhchap-new \
  confirm=true
salt-call --local ceph_nvmeof.host_create \
  nqn.2026-09.io.example:storage nqn.2026-09.io.example:host1 \
  dhchap_key_source=/run/secrets/host-dhchap \
  dhchap_controller_key_source=/run/secrets/controller-dhchap \
  psk_source=/run/secrets/host-psk
```

Files must be regular, non-symlink, UTF-8 files no larger than 1 MiB. The value
must be one non-empty line; trailing CR/LF is removed. For regular execution the
file resides where the Salt module runs. With salt-ssh it resides on the
controller. Secret values are never public Salt arguments or return values, and
credential-shaped fields are recursively removed from every response.

## Namespaces

Use `namespace_list`, `namespace_get`, and `namespace_io_stats` for reads.
`namespace_list_hosts` and `namespace_list_locations` return the current
controller's aggregate views and accept optional namespace-ID and UUID filters.

`namespace_create` supports an existing RBD image or `create_image=true`, the
RBD pool/data pool and RADOS namespace, byte sizes, namespace ID and UUID,
512-byte or 4096-byte blocks, load-balancing placement, visibility, read-only,
auto-resize and trash behavior. Current main also accepts paired `LUKS1`/`LUKS2`
`encryption_format` and `key_id` lists plus `encryption_algorithm`.

```bash
salt-call --local ceph_nvmeof.namespace_create \
  nqn.2026-09.io.example:storage vm-1 rbd \
  create_image=true rbd_image_size=10737418240 block_size=4096
salt-call --local ceph_nvmeof.namespace_set_qos \
  nqn.2026-09.io.example:storage 1 rw_ios_per_second=5000
salt-call --local ceph_nvmeof.namespace_resize \
  nqn.2026-09.io.example:storage 1 21474836480 confirm=true
salt-call --local ceph_nvmeof.namespace_add_host \
  nqn.2026-09.io.example:storage 1 nqn.2026-09.io.example:host1
salt-call --local ceph_nvmeof.namespace_change_visibility \
  nqn.2026-09.io.example:storage 1 false confirm=true
salt-call --local ceph_nvmeof.namespace_delete \
  nqn.2026-09.io.example:storage 1 confirm=true
```

The remaining actions are `namespace_delete_host`,
`namespace_change_load_balancing_group`, `namespace_change_location`,
`namespace_set_auto_resize`, `namespace_set_rbd_trash_image`,
`namespace_refresh_size`, and `namespace_unpin`. `namespace_update` maps to the
controller's compound `PATCH` endpoint and sends only explicitly supplied
fields. It can return a partial HTTP `202` response if one internal change fails.

Dashboard can return HTTP `202` task envelopes for create and delete operations.
The extension preserves the envelope and does not poll or repeat a request;
inspect asynchronous work with `ceph_task`.

## Declarative states

The current-only `ceph_nvmeof` state module manages the resources for which the
public controller provides a stable GET projection:

- `gateway_configured`
- `subsystem_present` and `subsystem_absent`
- `listener_present` and `listener_absent`
- `host_present` and `host_absent`
- `namespace_present` and `namespace_absent`

Every state reads before mutation and reads again afterward. An HTTP `202`
response is passed to `ceph_task.wait` before the post-read, so a loaded
`ceph_task.wait` execution function is required whenever Dashboard schedules an
asynchronous task. Salt test mode validates declarations and any secret source
needed by the planned operation, but sends no mutation. Live deletion always
requires `confirm: true`; create-only drift is replaced only with
`confirm_replace: true`.

`gateway_configured` manages the gateway log level and IO-statistics mode. It
requires `server_address` or the deprecated `routing_traddr`, which keeps the
GET and PUT requests bound to one gateway rather than an implicitly selected
member of a group.

```yaml
gateway-one-settings:
  ceph_nvmeof.gateway_configured:
    - name: gateway-one
    - server_address: gw1.example
    - log_level: warning
    - io_stats_enabled: true
```

The subsystem state compares its NQN and any declared serial, model, maximum
namespace count, automatic-listener networks, and DHCHAP-presence flag. Serial,
model, maximum count, and network masks have no public update route. Their drift
can therefore be repaired only by replacing an empty subsystem. A
`dhchap_key_source` installs a key when GET reports that none is present. Once a
key exists, the state does not rotate it because Ceph never returns material
that could prove equality. Replacement preserves omitted public create fields;
when the existing subsystem has a key, its source is required before deletion.

```yaml
nvme-subsystem:
  ceph_nvmeof.subsystem_present:
    - name: nqn.2026-09.io.example:storage
    - serial_number: SN-1
    - model_name: Ceph bdev Controller
    - max_namespaces: 128
    - network_mask:
        - 192.0.2.0/24
    - dhchap_key_source: /run/secrets/subsystem-dhchap
    - confirm: true
```

For listeners, `name` is the subsystem NQN and the GET identity is the gateway
host, transport address, and TCP port. Address family and secure mode are exact
managed fields. Since the controller has no update route, drift uses a
confirmed delete/create replacement.

```yaml
gateway-one-listener:
  ceph_nvmeof.listener_present:
    - name: nqn.2026-09.io.example:storage
    - host_name: gw1
    - traddr: 192.0.2.10
    - trsvcid: 4420
    - adrfam: 0
    - secure: true
    - confirm_replace: true
```

For hosts, `name` is the host NQN and `subsystem_nqn` identifies the allowlist.
The three authentication inputs are absolute source files. The state compares
only `use_dhchap`, `use_psk`, and the `Host Specific` controller-key origin; it
never exposes a file path or secret value in `changes`. Missing DHCHAP keys can
be installed with `confirm: true`. TLS-PSK has no public update endpoint, so a
missing PSK needs `confirm_replace: true`; replacement is refused if it would
drop an existing host-specific key for which no source was supplied.

```yaml
initiator-one:
  ceph_nvmeof.host_present:
    - name: nqn.2026-09.io.example:host1
    - subsystem_nqn: nqn.2026-09.io.example:storage
    - dhchap_key_source: /run/secrets/host1-dhchap
    - dhchap_controller_key_source: /run/secrets/host1-controller-dhchap
    - psk_source: /run/secrets/host1-psk
    - confirm: true
    - confirm_replace: true
```

Namespace state IDs use the numeric namespace ID in `name`. Image and pool
identity, data pool, RADOS namespace, UUID when declared, block size, read-only
mode, and encryption entries are create-only. Size, pinned load-balancing group,
QoS, RBD trash behavior, location, automatic visibility, automatic resize, and
an optional exact host list use the corresponding public action routes. Changes
that resize, repin, revoke access, alter visibility, location, or trash behavior
require `confirm: true`. Create-only drift requires `confirm_replace: true`;
`force_replace: true` asks Ceph to remove the backing image as part of that
replacement. During replacement the state preserves an undeclared UUID, image
size for the same image, QoS limits, exact host grants, and pinned placement,
then verifies them after recreation.

```yaml
namespace-one:
  ceph_nvmeof.namespace_present:
    - name: 1
    - subsystem_nqn: nqn.2026-09.io.example:storage
    - rbd_image_name: vm-1
    - rbd_pool: rbd
    - create_image: true
    - rbd_image_size: 10737418240
    - block_size: 4096
    - load_balancing_group: 2
    - rw_ios_per_second: 5000
    - trash_image: true
    - auto_visible: false
    - hosts:
        - nqn.2026-09.io.example:host1
    - confirm: true
    - confirm_replace: true
```

Gateway statistics, SPDK log settings, connections, namespace IO statistics,
refresh actions, and all CLI-only or UI-only methods remain operational
execution functions. They are not declared as resources by the state module.
`gw_group` and `server_address` select a gateway for every state. Subsystem,
host, and namespace states also accept `routing_traddr` for the controller's
deprecated routing parameter; listener `traddr` always means the listener's
transport address.

## Compatibility boundary

The current controller exposes `del_key`, `add_network`, `del_network`,
`add_kmip_server_endpoint`, `del_kmip_server_endpoint`, `list_eps`,
`get_subsystems`, `get_io_stats`, and `reset_io_stats` only as Ceph CLI commands.
They have no versioned `/api` route and are intentionally not invented here.

The four initiator helpers also use the internal UI router and are excluded:

- `POST /ui-api/nvmeof/subsystem/{subsystem_nqn}/host`
- `DELETE /ui-api/nvmeof/subsystem/{subsystem_nqn}/host/{host_nqn}`
- `POST /ui-api/nvmeof/namespace/{nsid}/host`
- `DELETE /ui-api/nvmeof/namespace/{nsid}/host`

`GET /ui-api/nvmeof/status` is excluded with the rest of that unversioned UI
contract.

The repository OpenAPI snapshot contains 25 earlier NVMe-oF routes. Compared
with that snapshot, current main adds gateway
statistics, IO-stat mode, listener inspection, thread statistics and network
refresh; subsystem key rotation; the listener port in its delete resource ID;
four host-key actions; all namespace action endpoints; UUID and aggregate
namespace filters; and the newer subsystem/namespace creation fields.

The contracts follow the
[current Ceph controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/nvmeof.py),
the [Ceph REST API reference](https://docs.ceph.com/en/latest/mgr/ceph_api/), and
the [Ceph NVMe-oF gateway guide](https://docs.ceph.com/en/latest/rbd/nvmeof-overview/).
