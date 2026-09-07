# Security policy

## Supported versions

Until the first stable release, security fixes are made on the latest release
and the `main` branch. After stable releases begin, this file will list the
supported release lines explicitly.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** form in the repository Security tab to
open a private security advisory. Do not file a public issue for a vulnerability
that could expose Ceph credentials, permit an unintended API request, bypass a
confirmation guard, or disclose Salt pillar/job data.

Include the affected `saltext.ceph`, Salt, Python, and Ceph versions, the loader
type (minion, master, local, or salt-ssh), and a minimal reproduction. Remove all
real Dashboard tokens, passwords, keyrings, certificates with private keys,
hostnames, and cluster FSIDs before attaching logs or state output.

The maintainers will acknowledge the report through the private advisory,
assess affected versions, prepare a fix and regression test, and coordinate a
release before public disclosure.
