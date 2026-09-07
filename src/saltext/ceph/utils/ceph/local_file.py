"""Bounded local file input for Ceph API payloads."""

import os
from pathlib import Path

from saltext.ceph.utils.ceph.errors import ConfigurationError

MAX_TEXT_FILE_SIZE = 16 * 1024 * 1024


def read_text(source):
    """Read UTF-8 text from an absolute regular non-symlink file."""
    if not isinstance(source, (str, os.PathLike)):
        raise ConfigurationError("source must be a filesystem path.")
    path = Path(source)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ConfigurationError("source must be an absolute regular file, not a symlink.")
    try:
        if path.stat().st_size > MAX_TEXT_FILE_SIZE:
            raise ConfigurationError("Input file exceeds the 16 MiB size limit.")
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(f"Unable to read input file: {exc.__class__.__name__}.") from None
    if "\x00" in value:
        raise ConfigurationError("Input file contains a NUL byte.")
    return value
