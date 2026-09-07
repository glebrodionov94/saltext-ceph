# Installation

`saltext.ceph` must be installed in the Python environment of the Salt process
that calls Ceph Dashboard. One control minion, one masterless node, or the
salt-ssh controller is sufficient for a cluster. API-based management does not
require a Salt minion on every Ceph host.

Install the published package in the Python environment used by Salt:

```console
salt-pip install saltext.ceph
```

With a classic Salt installation, use its Python interpreter instead:

```console
python -m pip install saltext.ceph
```

## Development checkout

```console
git clone https://github.com/glebrodionov94/saltext-ceph.git
cd saltext-ceph
uv venv --python 3.11
uv pip install -e ".[tests,dev,docs,build]" "salt==3006.27"
```

Activate `.venv` before running Python or the development tools. See
[Development](development.md) for platform-specific commands and validation.

## Install a built wheel

Build the package from a clean checkout:

```console
python -m build
```

For a Salt onedir installation, install the resulting wheel with its bundled
package installer:

```console
salt-pip install dist/saltext_ceph-*.whl
```

For a classic installation, invoke that installation's interpreter:

```console
python -m pip install dist/saltext_ceph-*.whl
```

Install on the salt-ssh controller to use wrappers, on a Salt master to use
runners, and on a control minion or masterless node to use execution modules,
states, and beacons. A single machine may provide several of these roles.

Restart long-running Salt processes after installing or upgrading the extension,
then verify loader discovery:

```console
salt-call --local sys.list_modules
salt-call --local sys.list_state_modules
salt-run sys.list_functions ceph
```

Configure the Dashboard connection only after installation. The
[API client guide](api-client.md) describes profiles, authentication, TLS, and
salt-ssh behavior; the [GitOps guide](gitops.md) describes the recommended
single-control-minion layout.
