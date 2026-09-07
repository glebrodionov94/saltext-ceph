"""Bounded local text input tests."""

import pytest

from saltext.ceph.utils.ceph import local_file
from saltext.ceph.utils.ceph.errors import ConfigurationError


def test_read_text_accepts_empty_utf8_file(tmp_path):
    source = tmp_path / "empty"
    source.write_text("", encoding="utf-8")
    assert local_file.read_text(source) == ""


@pytest.mark.parametrize("value", [b"bad\x00data", b"\xff"])
def test_read_text_rejects_invalid_data(tmp_path, value):
    source = tmp_path / "payload"
    source.write_bytes(value)
    with pytest.raises(ConfigurationError):
        local_file.read_text(source)


def test_read_text_requires_absolute_regular_file():
    with pytest.raises(ConfigurationError):
        local_file.read_text("relative")
