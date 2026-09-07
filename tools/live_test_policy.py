"""Pure path and option policy for the credential-bearing Nox live session."""

from pathlib import Path

_SAFE_LONG_OPTIONS = frozenset(
    (
        "--cache-clear",
        "--ceph-live",
        "--ceph-live-destructive",
        "--ceph-live-mutate",
        "--collect-only",
        "--disable-warnings",
        "--exitfirst",
        "--ff",
        "--lf",
        "--nf",
        "--no-header",
        "--no-summary",
        "--quiet",
        "--strict-config",
        "--strict-markers",
        "--verbose",
    )
)
_SAFE_LONG_VALUE_OPTIONS = frozenset(
    ("--color", "--durations", "--durations-min", "--keyword", "--markexpr", "--maxfail", "--tb")
)
_SAFE_SHORT_OPTIONS = frozenset(("-k", "-m", "-q", "-qq", "-v", "-vv", "-x"))


def isolated_pytest_environment(outer_environment, session_environment, live_environment):
    """Return a pytest env which masks ambient pytest controls and Python paths."""
    environment = dict.fromkeys(
        {
            name
            for source in (outer_environment, session_environment)
            for name in source
            if name.startswith("PYTEST_")
        }
    )
    environment.update(
        {
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONPATH": None,
            **live_environment,
        }
    )
    return environment


def is_unsafe_option(argument):
    """Return whether a pytest option can escape isolation or expose values."""
    if not isinstance(argument, str):
        return True
    if argument.startswith("@"):
        return True
    if argument == "--":
        return True
    if argument.startswith("-") and not argument.startswith("--"):
        return argument not in _SAFE_SHORT_OPTIONS
    if argument.startswith("--"):
        return not (
            argument in _SAFE_LONG_OPTIONS
            or argument in _SAFE_LONG_VALUE_OPTIONS
            or any(argument.startswith(f"{option}=") for option in _SAFE_LONG_VALUE_OPTIONS)
        )
    return False


def validate_test_path(argument, repo_root):
    """Validate a possible pytest path and return whether it is one.

    Existing directories count as paths even when their names have no suffix.
    Resolving both sides prevents traversal and symlink escapes.
    """
    if not isinstance(argument, str):
        raise ValueError("The live session accepts string arguments only.")
    raw_candidate = argument.split("::", 1)[0]
    candidate = Path(raw_candidate)
    normalized = raw_candidate.replace("\\", "/")
    looks_like_path = (
        "::" in argument
        or candidate.suffix == ".py"
        or candidate.is_absolute()
        or candidate.exists()
        or normalized.rstrip("/") == "tests/integration"
        or normalized.startswith("tests/integration/")
    )
    if not looks_like_path:
        return False
    if not candidate.exists():
        raise ValueError("The requested live-test path does not exist.")
    allowed_root = (Path(repo_root) / "tests" / "integration").resolve()
    try:
        candidate.resolve().relative_to(allowed_root)
    except ValueError:
        raise ValueError(
            "The live session only accepts test paths below tests/integration."
        ) from None
    return True
