# Contributing

Thank you for contributing to `saltext.ceph`. The extension is intended for
declarative Ceph management through the Dashboard REST API, so changes should
preserve Salt loader conventions, idempotent state behavior, and safe handling
of credentials and destructive operations.

## Development setup

Use Python 3.10 or newer. A local environment can be prepared with `uv`:

```console
uv venv --python 3.11
uv pip install -e ".[tests,dev,docs,build]" "salt==3006.27"
```

Run the focused tests while developing, then run the repository checks before
opening a pull request:

```console
pre-commit run --all-files
pytest tests/unit -q
python -m sphinx -W --keep-going -b html docs docs/_build/html
python -m build
uvx --with "packaging>=24.2" twine check --strict dist/*
uvx check-wheel-contents dist/*.whl
python tools/check_dist.py dist
```

The CI matrix performs the supported Salt/Python combinations and rebuilds a
wheel from the source distribution. Keep external GitHub Actions pinned to full
commit hashes; Dependabot maintains those pins.

## Changes

- Add unit tests for execution, wrapper, runner, beacon, and state behavior that
  changes. Keep live Ceph tests opt-in and read-only unless a test environment
  explicitly authorizes mutation.
- Preserve Dashboard endpoint media types and release gates. Explain a
  release-specific route in the module documentation and tests.
- Keep secrets out of source, examples, fixtures, Salt output, and task data.
  Use file-backed secret arguments where the extension provides them.
- Require an explicit confirmation argument for destructive API operations and
  preserve Salt test mode in states and GitOps runners.
- Add a [Towncrier fragment][changelog] for user-visible changes. Do not edit
  released changelog entries by hand.
- Update documentation for new public functions and run the generated reference
  page hook.

Report security issues through the private process in [SECURITY.md], rather
than a public issue. By contributing, you agree that your work is licensed
under the repository's Apache-2.0 license and follows the
[Contributor Covenant](CODE-OF-CONDUCT.md).

The [Salt contributing guide][salt-contributing] applies where this repository
does not define a project-specific rule.

[changelog]: https://salt-extensions.github.io/salt-extension-copier/topics/documenting/changelog.html
[salt-contributing]: https://docs.saltproject.io/en/master/topics/development/contributing.html
