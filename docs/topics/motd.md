# Dashboard message of the day

Current Ceph exposes public endpoints for setting and clearing the Dashboard
message of the day:

```bash
salt-call --local ceph_motd.create warning 2h 'Maintenance starts soon'
salt-call --local ceph_motd.clear confirm=true
```

`severity` is `info`, `warning`, or `danger`. `expires` is `0` for no expiry or
a relative duration such as `30s`, `2h`, `10d`, or `4w`. Message text is bounded
to 64 KiB before any HTTP request. Clearing the message permanently discards its
text and requires the exact boolean `confirm=true`.

The public API does not expose a matching read operation; Dashboard reads the
message through a private `/ui-api` route. Consequently, MOTD operations remain
imperative and the extension does not provide a state that would pretend it can
detect drift or verify convergence. These endpoints are absent in Ceph Reef.

The implementation follows the public controller in the
[current MOTD plugin](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/plugins/motd.py)
and Ceph's [generated REST API reference](https://docs.ceph.com/en/latest/mgr/ceph_api/#motd).
