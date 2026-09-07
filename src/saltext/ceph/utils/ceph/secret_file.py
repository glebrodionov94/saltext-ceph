"""Small, explicit file boundary for secret-bearing Ceph API operations."""

import os
import tempfile
from pathlib import Path

from saltext.ceph.utils.ceph.errors import ConfigurationError

MAX_SECRET_FILE_SIZE = 1024 * 1024


def read(source):
    """Read a small UTF-8 secret from an absolute, regular, non-symlink file."""
    if not isinstance(source, (str, os.PathLike)):
        raise ConfigurationError("source must be a filesystem path.")
    path = Path(source)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ConfigurationError("source must be an absolute regular file, not a symlink.")
    try:
        if path.stat().st_size > MAX_SECRET_FILE_SIZE:
            raise ConfigurationError("Secret file exceeds the 1 MiB size limit.")
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(f"Unable to read secret file: {exc.__class__.__name__}.") from None
    if not value.strip() or "\x00" in value:
        raise ConfigurationError("Secret file is empty or invalid.")
    return value


def write(destination, value, overwrite=False):
    """Atomically write UTF-8 secret text with mode 0600 where supported."""
    if not isinstance(destination, (str, os.PathLike)):
        raise ConfigurationError("destination must be a filesystem path.")
    if not isinstance(overwrite, bool):
        raise ConfigurationError("overwrite must be a boolean.")
    path = Path(destination)
    if not path.is_absolute() or not path.parent.is_dir() or path.is_symlink():
        raise ConfigurationError(
            "destination must be an absolute path in an existing directory, not a symlink."
        )
    if path.exists() and not overwrite:
        raise ConfigurationError("destination already exists; set overwrite=True to replace it.")
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ConfigurationError("Secret value is empty or invalid.")
    descriptor = None
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            descriptor = None
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise ConfigurationError("destination was created concurrently.") from None
            os.unlink(temporary)
        temporary = None
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(
            f"Unable to write secret file: {exc.__class__.__name__}."
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return str(path)
