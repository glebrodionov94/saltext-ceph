# Releasing

Releases are built by GitHub Actions and published with PyPI Trusted Publishing.
No long-lived PyPI token is accepted by the workflow. The repository variable
`CEPH_RELEASES_ENABLED` is an additional circuit breaker and must remain unset or
set to a value other than `true` until the release environments are configured.

The pipeline follows the Salt Extension Copier layout: a tag workflow runs the
normal CI and produces immutable artifacts, then the top-level
`deploy-package-action.yml` workflow downloads those artifacts. The publishing
jobs do not check out or build source code and receive only `actions: read` and
`id-token: write`. PyPI receives provenance attestations for every uploaded file.

## One-time repository and index setup

Complete these steps before setting `CEPH_RELEASES_ENABLED=true`:

1. Push an initial commit to the public repository. Releases require Git history
   because `setuptools-scm` derives the version from an exact `vMAJOR.MINOR.PATCH`
   tag. The local fallback version exists only so an empty development checkout
   can be built.
2. Create GitHub environments named `testpypi` and `release`. Require a trusted
   maintainer's approval for every deployment to `release`. Consider requiring
   approval for `testpypi` as well.
3. Configure a pending Trusted Publisher on both package indexes. TestPyPI uses a
   separate account and configuration from PyPI.

   | Setting | TestPyPI | PyPI |
   | --- | --- | --- |
   | PyPI project name | `saltext.ceph` | `saltext.ceph` |
   | GitHub owner | `glebrodionov94` | `glebrodionov94` |
   | GitHub repository | `saltext-ceph` | `saltext-ceph` |
   | Workflow filename | `deploy-package-action.yml` | `deploy-package-action.yml` |
   | Environment | `testpypi` | `release` |

   Pending publishers can create the projects on the first upload. Recheck that
   the project name is still available immediately before registering them.
4. Do not create `PYPI_API_TOKEN` or `TEST_PYPI_API_TOKEN` repository secrets.
   Revoke any PyPI token that has been pasted into a message, terminal, issue, or
   other place outside the package index.
5. Protect `main` with the CI status check and review changes to
   `.github/workflows/deploy-package-action.yml`. Protect tags matching `v*` so
   only maintainers can create or delete release tags.
6. Set the repository variable `CEPH_RELEASES_ENABLED` to `true` only after a
   test-cluster validation and a review of the release artifacts.

The Trusted Publisher identity must match all five values in the table exactly.
Renaming the repository, workflow, or GitHub environment requires updating the
publisher configuration on both indexes.

## Validate a release candidate

Run the same local checks used by CI:

```console
python -m pytest tests/unit -q
python -m pre_commit run --all-files
python -m sphinx -W --keep-going -b html docs docs/_build/html
uv run --no-project --isolated \
  --with-requirements tools/requirements-release.txt \
  python -m build --outdir dist
uv run --no-project --isolated \
  --with-requirements tools/requirements-release.txt \
  python -m twine check --strict dist/*
uv run --no-project --isolated \
  --with-requirements tools/requirements-release.txt \
  python -m check_wheel_contents dist/*.whl
python tools/check_dist.py dist
```

Keep release tooling isolated from the Python environment that runs Salt. Salt
3006 constrains an older `packaging` release, while the wheel metadata uses the
current PEP 639 license fields. The pinned release requirements match the build
job and avoid validating the archives with a stale metadata parser.

`tools/check_dist.py` requires exactly one wheel and one source distribution. It
checks their name, version, license, dependencies, Salt loader entry point,
Python source inventory, the absence of local API specifications, bytecode, and
`.env` files, and scans archive contents for common long-lived credentials without
printing matched values. CI also rebuilds a wheel from the sdist and installs the
wheel with all runtime dependencies in a clean virtual environment.

Keep one Towncrier fragment in `changelog/` for each change. The first release is
expected to be `0.1.0`; later versions follow Semantic Versioning. Only stable
`MAJOR.MINOR.PATCH` versions are accepted by the release workflows.

## Automated release PR

When releases are enabled, a successful push to `main` with news fragments calls
`prepare-release-action.yml`. It renders `CHANGELOG.md` and creates or updates
`release/auto`. Review the complete changelog and CI result before merging that
PR. Merging it creates an annotated version tag and runs the release pipeline.

For a personal repository without an autorelease GitHub App, the PR created with
the default `GITHUB_TOKEN` might not start pull-request workflows automatically.
In that case, use the manual procedure below or configure a GitHub App with only
the repository permissions needed to create the release PR. Store its app ID and
private key as `AUTORELEASE_CLID` and `AUTORELEASE_PRIV` only if this automation
is required.

## Manual release

Build and review the changelog on a branch:

```console
towncrier build --yes --version 0.1.0
python tools/version.py
```

Commit the rendered changelog, merge it into `main`, and verify that no visible
news fragments remain. From the exact, tested `main` commit, create and push a
signed or annotated tag:

```console
git tag -s v0.1.0
git push origin v0.1.0
```

The tag workflow verifies the changelog and runs the full CI. After it succeeds,
the release workflow publishes the same artifacts to TestPyPI, waits for the
`release` environment approval, publishes to PyPI, and creates a GitHub Release
with the wheel, sdist, and `SHA256SUMS`.

## Failed or incorrect releases

Published PyPI files cannot be replaced. If a release is incorrect, yank it and
publish a fixed version. If PyPI succeeds but GitHub Release creation fails,
create the GitHub Release from the original workflow artifacts while they are
still retained; do not rebuild different files under the same version. Package
artifacts are retained for 14 days.

PyPI's [Trusted Publishing guide](https://docs.pypi.org/trusted-publishers/), the
[PyPA GitHub Actions guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/),
and the [Salt Extension publishing guide](https://salt-extensions.github.io/salt-extension-copier/topics/publishing.html)
describe the external settings and release model used here.
