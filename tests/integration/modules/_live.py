"""Shared helpers for opt-in, read-only Dashboard module tests."""

from collections.abc import Mapping

import salt.config
import salt.loader

from saltext.ceph.utils import ceph as ceph_utils
from saltext.ceph.utils.ceph.client import APIResponse


def response_data(response, expected_type):
    """Validate the common typed-utils response contract and return its data."""
    assert isinstance(response, APIResponse)
    assert 200 <= response.status < 300
    assert isinstance(response.headers, dict)
    assert isinstance(response.data, expected_type)
    return response.data


def mapping_items(response):
    """Return a validated list whose members are mappings."""
    items = response_data(response, list)
    assert all(isinstance(item, Mapping) for item in items)
    return items


def load_execution_modules(tmp_path, monkeypatch, live_client):
    """Load this extension with Salt while routing API access to the live client.

    The Salt opts stay free of credentials. Patching the shared client factory
    still exercises entry-point discovery, the execution module, its API
    composition layer, and the real typed HTTP utility.
    """

    root_dir = tmp_path / "live-minion"
    opts = salt.config.DEFAULT_MINION_OPTS.copy()
    opts["__role"] = "minion"
    opts["id"] = "saltext-ceph-live-readonly"
    opts["root_dir"] = str(root_dir)
    for name in ("cachedir", "pki_dir", "sock_dir", "conf_dir"):
        directory = root_dir / name
        directory.mkdir(parents=True)
        opts[name] = str(directory)
    opts["log_file"] = "logs/minion.log"
    opts["conf_file"] = str(root_dir / "conf_dir" / "minion")

    def get_live_client(_opts, _pillar, _context, _profile="default"):
        return live_client

    monkeypatch.setattr(ceph_utils, "get_client", get_live_client)
    return salt.loader.minion_mods(opts, context={})
