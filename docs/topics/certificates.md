# Cephadm certificates

The `ceph_certificates` execution module reads certificates managed by cephadm
through Dashboard's `/api/service/certificate` controller. It provides metadata,
expiration state, service certificate details, and the public cephadm root CA.
The controller does not expose private keys.

```bash
salt-call --local ceph_certificates.list
salt-call --local ceph_certificates.list status=expiring scope=service
salt-call --local ceph_certificates.list service_type='rgw*' \
  include_cephadm_signed=true
salt-call --local ceph_certificates.get rgw.site-a
salt-call --local ceph_certificates.root_ca
```

Supported status filters are `expired`, `expiring`, `valid`, `invalid`, and
`not_configured`. Supported scopes are `service`, `host`, and `global`; matching
is case insensitive. `service_type` supports `*` and `?` wildcards while rejecting
characters that could alter cephadm's comma-separated filter expression.

All calls are read-only, accept an optional `profile`, use API version `1.0`, and
return the common `status`, `data`, and `headers` envelope. The root CA is returned
as public PEM text in `data`.

This controller exists in [current Ceph](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/controllers/certificate.py)
and is covered by the [Dashboard certificate tests](https://github.com/ceph/ceph/blob/main/src/pybind/mgr/dashboard/tests/test_certificate.py).
It is absent from Ceph Reef and from the OpenAPI document captured from the Reef
test cluster. Those releases will return the normal Dashboard HTTP error.
