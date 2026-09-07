# RGW notification topics

`ceph_rgw_topic` exposes the current public Dashboard topic controller:

| Function | Dashboard request | API version |
| --- | --- | --- |
| `list_topics` | `GET /api/rgw/topic` | `1.0` |
| `get_topic` | `GET /api/rgw/topic/{key}` | `1.0` |
| `create_topic` | `POST /api/rgw/topic` | `1.0` |
| `delete_topic` | `DELETE /api/rgw/topic/{key}` | `1.0` |

This Dashboard controller is present on current main and absent from Reef's
`controllers/rgw.py`, although Reef RGW itself supports bucket notifications.
Use it only after verifying the Dashboard release.

Topic keys such as `owner:topic_name` are percent-encoded as one route segment.
Creation supports HTTP, AMQP, and Kafka endpoint fields, persistent delivery,
retry limits, CloudEvents, TLS verification, and a topic policy.

```bash
salt-call --local ceph_rgw_topic.create_topic alerts \
  owner=alice push_endpoint_source=/run/secrets/rgw-push-endpoint \
  persistent=true verify_ssl=true
salt-call --local ceph_rgw_topic.get_topic alice:alerts
salt-call --local ceph_rgw_topic.delete_topic alice:alerts confirm=true
```

Push endpoint URIs may contain credentials, and opaque data may carry private
integration material. Creation therefore accepts them through
`push_endpoint_source` and `opaque_data_source`; each must be an absolute path
to a regular, non-symlink UTF-8 file. Both fields are redacted from
list/get/create responses unless `include_secrets=true`. Deletion requires
`confirm=true`.

The implementation follows the [current Dashboard controller](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/rgw.py)
and [Ceph bucket-notification documentation](https://docs.ceph.com/en/latest/radosgw/notifications/).
