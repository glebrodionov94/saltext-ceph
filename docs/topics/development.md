# Development

## Scope

`saltext.ceph` integrates Salt with the Ceph Dashboard REST API. The source tree
contains a shared HTTP client in `utils/ceph/`, execution modules, declarative
states, and controller-side salt-ssh wrappers. See [API client](api-client.md)
for the transport interface and validation boundaries.

## Environment

The package targets Python 3.10+ and Salt 3006+. The template's CI matrix tests
specific Salt/Python combinations on Linux, macOS, and Windows. Linux is the
Ceph server platform; the OS matrix concerns the Python extension and its Salt
environment. Individual resource guides document their Ceph API compatibility.

Create the environment with `uv venv --python 3.11`, then install dependencies:

```console
uv pip install -e ".[tests,dev,docs,build]" "salt==3006.27"
```

On Linux/macOS, activate with `source .venv/bin/activate`. In PowerShell, use
`.venv\Scripts\Activate.ps1`. Activation is optional if commands use the full
interpreter path: `.venv/bin/python` or `.venv\Scripts\python.exe`.

The `lint` and `dev_extra` extras install Pylint and the pinned formatting and
coverage tools. The template also supplies `tools/initialize.py`, `make dev`,
and `.envrc.example` for automated setup.

## Tests and lint

```console
python -m pytest tests/unit -q
nox -e tests-3
nox -e lint
python -m pre_commit install
python -m pre_commit run --all-files
```

Pre-commit checks Git-tracked files. Before the first commit, stage the files you
intend to commit, or pass paths explicitly using `pre-commit run --files ...`.
The local credential hook rejects common PyPI, GitHub, and AWS tokens and private
key headers while suppressing matched values from its output.

The unit suite covers package installation, connection profiles, HTTP protocol
behavior, and actual Salt utility/SSH loaders. Loopback HTTP tests verify Requests
serialization and session behavior without a cluster. The functional and
integration directories retain upstream fixtures; they do not start daemons
unless a test requests them. The live Dashboard smoke tests are read-only and
skip unless `CEPH_TEST_URL` is set. Configure either `CEPH_TEST_TOKEN`, or both
`CEPH_TEST_USERNAME` and `CEPH_TEST_PASSWORD`; set `CEPH_TEST_EXPECTED_FSID` to
pin the intended test cluster. `CEPH_TEST_VERIFY` accepts `true`, `false`, or a
CA bundle path. Plain HTTP additionally requires `CEPH_TEST_ALLOW_HTTP=1`.

```console
CEPH_TEST_URL=https://ceph-test.example:8443 \
CEPH_TEST_TOKEN=... \
CEPH_TEST_EXPECTED_FSID=00000000-0000-0000-0000-000000000000 \
python -m pytest tests/integration/test_live_dashboard.py -q
```

Keep these values outside Git. The smoke tests only read minimal health and the
cluster FSID. Mutating acceptance tests require a separately isolated cluster
and are not enabled by these variables.

`SALT_REQUIREMENT` selects a Salt version for Nox. For example, set it to
`salt==3006.27` and use Python 3.11 to test the older CI target.

Nox defaults to Salt 3006.27 on Windows, where Salt 3008's `timelib` dependency
requires Microsoft C++ Build Tools. CI selects Salt versions explicitly.
The manual setup above uses the older target to avoid this compiler dependency.
The upstream automatic environment initializer instead selects Python 3.14;
use the manual setup to keep a Python 3.11 environment.

## Documentation and packages

```console
python -m sphinx -W --keep-going -b html docs docs/_build/html
python -m build
uvx twine check --strict dist/*
uvx check-wheel-contents dist/*.whl
python tools/check_dist.py dist
```

The generated `nox -e docs` session also checks external links and documentation
coverage and requires `make`. On Linux, the spelling extension may require the
system Enchant library (for example, `libenchant-2-2` on Debian/Ubuntu).

Run Twine through `uvx` in its own environment: current Salt releases pin an
older `packaging` library, while current Twine needs a newer one to validate
modern distribution metadata. CI likewise checks artifacts separately from Salt.

Package versions are derived from Git tags using `setuptools-scm`; do not edit
`src/saltext/ceph/version.py`. A development fallback allows building before the
first Git commit. It must not be used as a substitute for a release tag.

`tools/check_dist.py` verifies the two expected archives, their matching name
and version, metadata, Salt loader entry point, licence files, source coverage,
and the absence of development-only or secret-bearing files. Release CI also
rebuilds the wheel from the source distribution and installs the wheel in a
clean environment before either index receives it.

## Maintaining the scaffold

The source template and version are recorded in `.copier-answers.yml`. Follow
the [upstream update guide](https://salt-extensions.github.io/salt-extension-copier/topics/updating.html)
on a clean, committed branch when updating the boilerplate. Review generated
changes, especially release workflow conditions and dependency pins.

Local adjustments to the generated template include:

- Excluding example execution/state functions and their example tests.
- Adding package installation checks and generated reference pages for every
  loader type and utility module.
- Describing source installation while the project is unpublished.
- Gating publishing and automatic release PRs with `CEPH_RELEASES_ENABLED` and
  publishing through environment-scoped PyPI trusted publishers.
- Adding explicit source archive contents, Python 3 wheel metadata, and a
  development version fallback.
- Using current Setuptools for this package while applying Salt's legacy
  Setuptools compatibility constraint only when Salt itself is built.
- Using Pylint 4.0.6 to support the template's Isort 8 dependency.
- Honoring `SALT_REQUIREMENT` when installing lint/test extras and using the
  older Salt CI target by default for local Windows Nox sessions.
- Using the public GitHub noreply address recorded by Copier for package author
  and maintainer metadata.
- Making autodoc generation independent of Windows path separators and line endings.

Use Towncrier fragments for user-facing changes. For changes without an issue,
use a descriptive `+name.added` (or another supported category) filename in
`changelog/`. Generated documentation will include the unreleased draft.
