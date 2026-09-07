from pathlib import Path

import pytest

from tools import live_test_policy

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "argument",
    [
        "-l",
        "-s",
        "--showlocals",
        "--capture=no",
        "--pyargs",
        "-punsafe_plugin",
        "--rootdir=.",
        "--basetemp=outside",
        "--pastebin=failed",
        "-qsl",
        "-qpunsafe_plugin",
        "-qcunsafe.ini",
        "-qoshowlocals=true",
        "--",
        "--capt=no",
        "--unknown-plugin-option",
        "@pytest-args.txt",
    ],
)
def test_credential_bearing_pytest_rejects_unsafe_options(argument):
    assert live_test_policy.is_unsafe_option(argument)


@pytest.mark.parametrize(
    "argument",
    [
        "-q",
        "--collect-only",
        "--ceph-live-mutate",
        "--tb=short",
        "--maxfail",
        "-k",
        "live_core",
    ],
)
def test_credential_bearing_pytest_accepts_safe_filters(argument):
    assert not live_test_policy.is_unsafe_option(argument)


@pytest.mark.parametrize("path", [".", "tests", "tests/unit"])
def test_live_path_policy_rejects_existing_paths_outside_integration(path):
    with pytest.raises(ValueError, match="below tests/integration"):
        live_test_policy.validate_test_path(path, REPO_ROOT)


def test_live_path_policy_accepts_integration_directory_and_node_id():
    assert live_test_policy.validate_test_path("tests/integration", REPO_ROOT)
    assert live_test_policy.validate_test_path(
        "tests/integration/test_live_dashboard.py::test_live_health_is_a_mapping",
        REPO_ROOT,
    )


def test_live_path_policy_rejects_traversal_and_missing_python_path():
    with pytest.raises(ValueError, match="below tests/integration"):
        live_test_policy.validate_test_path("tests/integration/../../tests/unit", REPO_ROOT)
    with pytest.raises(ValueError, match="does not exist"):
        live_test_policy.validate_test_path("tests/integration/missing.py", REPO_ROOT)


def test_live_path_policy_ignores_non_path_filter_expression():
    assert not live_test_policy.validate_test_path("live_core", REPO_ROOT)


def test_live_pytest_environment_masks_every_ambient_pytest_control():
    environment = live_test_policy.isolated_pytest_environment(
        {
            "PYTEST_ADDOPTS": "--pyargs untrusted",
            "PYTEST_DEBUG": "1",
            "PYTHONPATH": "outside",
        },
        {"PYTEST_DEBUG_TEMPROOT": "outside"},
        {"CEPH_TEST_TOKEN": "test-token"},
    )

    assert environment == {
        "PYTEST_ADDOPTS": None,
        "PYTEST_DEBUG": None,
        "PYTEST_DEBUG_TEMPROOT": None,
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": None,
        "CEPH_TEST_TOKEN": "test-token",
    }
