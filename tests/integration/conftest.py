from pathlib import Path

import pytest

from saltext.ceph.utils.ceph.client import CephClient

from ._live import GuardedLiveClient
from ._live import LiveConfigurationError
from ._live import load_settings
from ._live import validate_flag_hierarchy


def pytest_addoption(parser):
    """Register explicit, cumulative live-cluster safety gates."""
    group = parser.getgroup("Ceph live tests")
    group.addoption(
        "--ceph-live",
        action="store_true",
        default=False,
        help="allow read-only tests to connect to an explicitly configured Ceph cluster",
    )
    group.addoption(
        "--ceph-live-mutate",
        action="store_true",
        default=False,
        help="allow live mutations when CEPH_TEST_EXPECTED_FSID is configured",
    )
    group.addoption(
        "--ceph-live-destructive",
        action="store_true",
        default=False,
        help="allow exact-FSID-confirmed, allowlisted destructive live tests",
    )


def _flags(config):
    return {
        "live": bool(config.getoption("ceph_live")),
        "mutate": bool(config.getoption("ceph_live_mutate")),
        "destructive": bool(config.getoption("ceph_live_destructive")),
    }


def pytest_configure(config):
    """Reject ambiguous flag combinations before tests can access credentials."""
    flags = _flags(config)
    try:
        validate_flag_hierarchy(**flags)
    except LiveConfigurationError as exc:
        raise pytest.UsageError(str(exc)) from None
    if flags["live"]:
        # Locals can include a ConnectionConfig or credentials assembled by a
        # test. Disable their display even if a caller supplied ``-l``.
        config.option.showlocals = False


def _is_named_live_test(item):
    path = Path(str(item.fspath))
    return "integration" in path.parts and path.name.startswith("test_live")


def _level(item):
    if item.get_closest_marker("ceph_live_destructive") is not None:
        return "destructive"
    if item.get_closest_marker("ceph_live_mutate") is not None:
        return "mutate"
    if item.get_closest_marker("ceph_live") is not None:
        return "live"
    if item.get_closest_marker("ceph_live_feature") is not None:
        return "live"
    return None


def pytest_collection_modifyitems(config, items):
    """Keep every live test inert unless its cumulative flags are present."""
    flags = _flags(config)
    for item in items:
        if _is_named_live_test(item) and item.get_closest_marker("ceph_live") is None:
            item.add_marker(pytest.mark.ceph_live)
        level = _level(item)
        if level is None:
            continue
        if not flags["live"]:
            item.add_marker(pytest.mark.skip(reason="requires explicit --ceph-live"))
        elif level in ("mutate", "destructive") and not flags["mutate"]:
            item.add_marker(pytest.mark.skip(reason="requires explicit --ceph-live-mutate"))
        elif level == "destructive" and not flags["destructive"]:
            item.add_marker(pytest.mark.skip(reason="requires explicit --ceph-live-destructive"))


def _required_features(item):
    required = []
    for marker in item.iter_markers("ceph_live"):
        features = marker.kwargs.get("features", ())
        if isinstance(features, str):
            features = (features,)
        required.extend(features)
    for marker in item.iter_markers("ceph_live_feature"):
        required.extend(marker.args)
    return tuple(required)


def _destructive_resources(item):
    resources = []
    for marker in item.iter_markers("ceph_live_destructive"):
        resources.extend(marker.args)
        configured = marker.kwargs.get("resources", ())
        if isinstance(configured, str):
            configured = (configured,)
        resources.extend(configured)
    return tuple(resources)


@pytest.fixture(scope="session")
def live_settings(request):
    """Return redacted settings only after the explicit live gate is open."""
    flags = _flags(request.config)
    try:
        return load_settings(**flags)
    except LiveConfigurationError as exc:
        raise pytest.UsageError(str(exc)) from None


@pytest.fixture(scope="session")
def _live_transport(live_settings):
    """Share one raw HTTP session, kept private behind per-test capabilities."""
    client = CephClient(live_settings.connection)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def live_client(request, live_settings, _live_transport):
    """Return a client whose method/path policy is bound to this pytest item."""
    level = _level(request.node) or "live"
    return GuardedLiveClient(
        _live_transport,
        live_settings,
        level=level,
        destructive_resources=_destructive_resources(request.node),
    )


@pytest.fixture(autouse=True)
def _enforce_live_requirements(request):
    """Validate feature and operation gates before a live test body executes."""
    level = _level(request.node)
    if level is None:
        return
    settings = request.getfixturevalue("live_settings")
    missing = settings.require_features(*_required_features(request.node))
    if missing:
        pytest.skip(
            "live cluster does not declare required feature(s): " + ", ".join(sorted(missing))
        )
    try:
        if level == "destructive":
            settings.require_destructive(*_destructive_resources(request.node))
        elif level == "mutate":
            settings.require_mutation()
    except LiveConfigurationError as exc:
        raise pytest.UsageError(str(exc)) from None


@pytest.fixture(scope="package")
def master(master):  # pragma: no cover
    with master.started():
        yield master


@pytest.fixture(scope="package")
def minion(minion):  # pragma: no cover
    with minion.started():
        yield minion


@pytest.fixture
def salt_run_cli(master):  # pragma: no cover
    return master.salt_run_cli()


@pytest.fixture
def salt_cli(master):  # pragma: no cover
    return master.salt_cli()


@pytest.fixture
def salt_call_cli(minion):  # pragma: no cover
    return minion.salt_call_cli()
