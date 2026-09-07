"""Protect package and release supply-chain invariants."""

import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = REPOSITORY_ROOT / ".github" / "workflows"
WORKFLOWS = tuple(
    sorted(path for path in WORKFLOW_ROOT.iterdir() if path.suffix in {".yaml", ".yml"})
)
ACTION_FILES = WORKFLOWS + tuple(
    sorted((REPOSITORY_ROOT / ".github" / "actions").rglob("action.y*ml"))
)
USES_PATTERN = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
PINNED_ACTION_PATTERN = re.compile(r"^[^@]+@[0-9a-f]{40}$")


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_workflows_declare_default_permissions(workflow):
    text = workflow.read_text(encoding="utf-8")
    assert re.search(r"^permissions:(?:\s*\{\})?\s*$", text, re.MULTILINE)


@pytest.mark.parametrize("automation", ACTION_FILES, ids=lambda path: path.name)
def test_external_actions_are_pinned_to_commits(automation):
    references = USES_PATTERN.findall(automation.read_text(encoding="utf-8"))
    unpinned = [
        reference
        for reference in references
        if not reference.startswith("./") and not PINNED_ACTION_PATTERN.fullmatch(reference)
    ]
    assert not unpinned


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_checkout_does_not_persist_credentials(workflow):
    lines = workflow.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if "uses: actions/checkout@" in line:
            assert any(
                "persist-credentials: false" in following
                for following in lines[index + 1 : index + 8]
            )


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_workflows_do_not_use_privileged_pull_request_target(workflow):
    assert "pull_request_target:" not in workflow.read_text(encoding="utf-8")


def test_container_images_are_digest_pinned():
    images = []
    for workflow in WORKFLOWS:
        images.extend(
            re.findall(
                r"^\s*image:\s*['\"]?([^'\"\s]+)",
                workflow.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )
    assert images
    assert all(re.search(r"@sha256:[0-9a-f]{64}$", image) for image in images)


def test_release_uses_only_trusted_publishing():
    release = (WORKFLOW_ROOT / "deploy-package-action.yml").read_text(encoding="utf-8")

    assert "password:" not in release
    assert "PYPI_API_TOKEN" not in release
    assert "TEST_PYPI_API_TOKEN" not in release
    assert release.count("id-token: write") == 2
    assert "name: testpypi" in release
    assert "name: release" in release
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in release
    assert "vars.CEPH_RELEASES_ENABLED == 'true'" in release


def test_docs_deploys_only_artifacts_from_validated_release_runs():
    deployment = (WORKFLOW_ROOT / "deploy-docs-action.yml").read_text(encoding="utf-8")

    assert "workflow_call:" not in deployment
    assert "workflow_run:" in deployment
    assert "github.event.workflow_run.conclusion == 'success'" in deployment
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in deployment
    assert "github.event.workflow_run.name == 'Tagged Releases'" in deployment
    assert "github.event.workflow_run.event == 'push'" in deployment
    assert "github.event.workflow_run.name == 'Auto PR Releases'" in deployment
    assert "github.event.workflow_run.event == 'pull_request'" in deployment
    assert "vars.CEPH_RELEASES_ENABLED == 'true'" in deployment
    assert "run-id: ${{ github.event.workflow_run.id }}" in deployment
    assert deployment.count("actions: read") == 1
    assert deployment.count("pages: write") == 1
    assert deployment.count("id-token: write") == 1
    assert "contents: write" not in deployment


def test_docs_session_checks_the_sphinx_coverage_builder_report():
    noxfile = (REPOSITORY_ROOT / "noxfile.py").read_text(encoding="utf-8")

    assert '"tools" / "check_docs_coverage.py"' in noxfile
    assert '"docs" / "_build" / "coverage" / "python.txt"' in noxfile
    assert '"_build", "html", "python.txt"' not in noxfile


def test_package_workflow_runs_all_distribution_checks():
    package = (WORKFLOW_ROOT / "package-action.yml").read_text(encoding="utf-8")

    for command in (
        "python -m build",
        "python -m twine check --strict",
        "python -m check_wheel_contents",
        "python tools/check_dist.py",
        "python -m pip wheel",
        "python -m pip check",
    ):
        assert command in package


def test_formatter_target_matches_project_metadata():
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)

    assert project["project"]["requires-python"] == ">= 3.10"
    assert project["tool"]["black"]["target-version"] == ["py310"]


def test_package_validation_uses_pep639_compatible_packaging():
    package = (WORKFLOW_ROOT / "package-action.yml").read_text(encoding="utf-8")
    requirements_file = REPOSITORY_ROOT / "tools" / "requirements-release.txt"
    requirement_lines = {
        line.strip()
        for line in requirements_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    requirements = {Requirement(line) for line in requirement_lines}

    assert "--requirement tools/requirements-release.txt" in package
    assert {requirement.name for requirement in requirements} == {
        "build",
        "check-wheel-contents",
        "packaging",
        "twine",
    }
    assert all(
        len(requirement.specifier) == 1 and next(iter(requirement.specifier)).operator == "=="
        for requirement in requirements
    )
    packaging_requirement = next(item for item in requirements if item.name == "packaging")
    assert Version(next(iter(packaging_requirement.specifier)).version) >= Version("24.2")
