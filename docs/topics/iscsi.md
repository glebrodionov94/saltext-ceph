# iSCSI targets

The `ceph_iscsi` execution module manages the public Dashboard iSCSI resources.
Ceph Dashboard proxies these operations to the `rbd-target-api` service on the
configured ceph-iscsi gateways. Configure those gateways in Dashboard before
using the module.

| Function | Dashboard request | API version |
| --- | --- | --- |
| `get_discovery_auth` | `GET /api/iscsi/discoveryauth` | `1.0` |
| `set_discovery_auth` | `PUT /api/iscsi/discoveryauth` | `1.0` |
| `list_targets` | `GET /api/iscsi/target` | `1.0` |
| `get_target` | `GET /api/iscsi/target/{target_iqn}` | `1.0` |
| `create_target` | `POST /api/iscsi/target` | `1.0` |
| `update_target` | `PUT /api/iscsi/target/{target_iqn}` | `1.0` |
| `delete_target` | `DELETE /api/iscsi/target/{target_iqn}` | `1.0` |

Target listing is not paginated. It returns the complete target collection.

```bash
salt-call --local ceph_iscsi.list_targets
salt-call --local ceph_iscsi.get_target iqn.2026-01.com.example:storage
```

Create accepts structured portals, disks, clients, groups, authentication, and
control mappings. The shape follows the object used by the Dashboard frontend:

```json
{
  "target_iqn": "iqn.2026-01.com.example:storage",
  "portals": [{"host": "gateway-a", "ip": "192.0.2.10"}],
  "target_controls": {"cmdsn_depth": 128},
  "acl_enabled": true,
  "auth": {"user": "", "password": "", "mutual_user": "", "mutual_password": ""},
  "disks": [
    {
      "pool": "rbd",
      "image": "disk-one",
      "backstore": "user:rbd",
      "controls": {"max_data_area_mb": 128},
      "lun": 0
    }
  ],
  "clients": [
    {
      "client_iqn": "iqn.2026-01.com.example:client-one",
      "luns": [{"pool": "rbd", "image": "disk-one"}],
      "auth": {"user": "", "password": "", "mutual_user": "", "mutual_password": ""}
    }
  ],
  "groups": []
}
```

Each client and group disk must refer to a disk in the target. Group members
must refer to configured clients, and a client can belong to only one group.
The gateway supplies release-specific limits for target and disk controls; the
extension validates safe JSON scalar values, and Ceph validates their names and
ranges against that live gateway configuration.

CHAP usernames contain 8 through 64 letters, digits, or `_.:@-` characters.
Passwords contain 12 through 16 letters, digits, or `_@/-` characters. Mutual
CHAP requires valid primary credentials. Four empty values disable discovery or
target authentication.

`set_discovery_auth` reads `password_source` and optional
`mutual_password_source` from absolute regular non-symlink files. Omit both
users and both sources to disable discovery authentication. Under salt-ssh the
paths are on the controller. Target and client CHAP values are nested in the
complete target document; keep those declarations in encrypted pillar rather
than a plain Git state file.

Ceph returns configured CHAP passwords from its read endpoints. The extension
recursively redacts those passwords by default in `get_discovery_auth`,
`get_target`, and `list_targets`, and marks mapping responses with
`redacted: true`. Use `include_secrets=true` only for an explicit recovery or
diagnostic operation: the values can then enter Salt output, job caches, debug
logs, and external returns.

## Declarative target state

`ceph_iscsi.present` treats the target document as a full replacement, matching
the Dashboard controller. It compares the complete public configuration and
reads the target again after a synchronous or asynchronous mutation. Updating
an existing target can disconnect initiators and therefore requires
`confirm_update: true`; creation does not.

```yaml+jinja
iqn.2024-01.com.example:database:
  ceph_iscsi.present:
    - portals:
        - host: gateway1
          ip: 192.0.2.10
        - host: gateway2
          ip: 192.0.2.11
    - acl_enabled: true
    - auth:
        user: chapuser1
        password: {{ pillar['iscsi']['chap_password'] | yaml_dquote }}
        mutual_user: ''
        mutual_password: ''
    - disks: []
    - clients: []
    - groups: []
    - confirm_update: true
```

Passwords may be held in encrypted pillar, but Dashboard returns them through
this API. The state uses them for comparison and replaces them with a fixed
marker in both test-mode and applied `changes`. Target deletion uses
`ceph_iscsi.absent` and requires `confirm: true`.

An iSCSI update is a whole-target replacement. Missing disk, client, or group
entries are removed; changing the IQN or some controls can make Ceph delete and
recreate target configuration. For that reason `update_target` requires
`confirm=true`. Strip runtime-only `info` fields returned by reads and submit
the complete desired configuration. Target deletion also requires
`confirm=true`:

```bash
salt-call --local ceph_iscsi.delete_target \
  iqn.2026-01.com.example:storage confirm=true
```

Ceph refuses deletion while the target has active sessions. Deleting the
target removes gateways, LUN mappings, clients, and groups from ceph-iscsi; it
does not delete the underlying RBD images.

Create, update, and delete are Dashboard tasks. They can return HTTP `202`,
which means accepted rather than complete. Follow the returned task through
`ceph_task`. A completed create commonly returns `201`, a completed update
`200`, and a completed delete `204`.

The local generated OpenAPI file describes `target_controls`, `acl_enabled`,
`auth`, `portals`, `disks`, `clients`, and `groups` as strings. The controller
indexes and iterates structured values, and the Dashboard frontend and
controller tests send JSON objects and arrays; this extension follows that real
contract. OpenAPI also lists discovery-auth values as query parameters and as a
JSON body. The Dashboard frontend and backend tests send one JSON body, so the
extension does the same.

The public iSCSI controller is identical between Reef and current Ceph at the
time this adapter was implemented. Ceph documents the iSCSI gateway as being in
maintenance since November 2022, so new features are not expected even though
the API remains available.

The implementation follows the
[current iSCSI controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/iscsi.py),
the [Reef iSCSI controller](https://github.com/ceph/ceph/blob/reef/src/pybind/mgr/dashboard/controllers/iscsi.py),
the [Dashboard iSCSI client](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/frontend/src/app/shared/api/iscsi.service.ts),
the [Dashboard setup documentation](https://docs.ceph.com/en/reef/mgr/dashboard/#enabling-iscsi-management),
and the [Reef iSCSI gateway documentation](https://docs.ceph.com/en/reef/rbd/iscsi-overview/).
