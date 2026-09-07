"""Small, explicit file boundary for secret-bearing Ceph API operations."""

import os
import stat
import tempfile
from pathlib import Path

from saltext.ceph.utils.ceph.errors import ConfigurationError

MAX_SECRET_FILE_SIZE = 1024 * 1024
_WINDOWS = os.name == "nt"
_READ_CHUNK_SIZE = 64 * 1024


def _read_flags():
    """Return flags that keep secret descriptors private and reject links."""
    flags = os.O_RDONLY
    if _WINDOWS:
        return flags | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    try:
        flags |= os.O_NOFOLLOW | os.O_CLOEXEC
    except AttributeError:
        raise ConfigurationError("Secure secret file reads are unavailable.") from None
    return flags | getattr(os, "O_NONBLOCK", 0)


def _is_windows_reparse(file_stat):
    """Return whether a Windows stat result represents a reparse point."""
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(file_stat, "st_file_attributes", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _windows_file_identity(file_stat):
    """Return a comparable Windows file identity when Python exposes one."""
    device = getattr(file_stat, "st_dev", None)
    inode = getattr(file_stat, "st_ino", None)
    if device is None or not inode:
        return None
    return device, inode


def _validate_regular(file_stat):
    if not stat.S_ISREG(file_stat.st_mode):
        raise ConfigurationError("source must be an absolute regular file, not a symlink.")
    if file_stat.st_size > MAX_SECRET_FILE_SIZE:
        raise ConfigurationError("Secret file exceeds the 1 MiB size limit.")


def _read_descriptor(descriptor):
    """Read no more than the configured limit from an already validated fd."""
    value = bytearray()
    while len(value) <= MAX_SECRET_FILE_SIZE:
        remaining = MAX_SECRET_FILE_SIZE + 1 - len(value)
        chunk = os.read(descriptor, min(_READ_CHUNK_SIZE, remaining))
        if not chunk:
            break
        value.extend(chunk)
    if len(value) > MAX_SECRET_FILE_SIZE:
        raise ConfigurationError("Secret file exceeds the 1 MiB size limit.")
    return bytes(value)


def read(source):
    """Read a small UTF-8 secret from an absolute, regular, non-symlink file."""
    if not isinstance(source, (str, os.PathLike)):
        raise ConfigurationError("source must be a filesystem path.")
    try:
        path = Path(source)
    except (OSError, TypeError, ValueError):
        raise ConfigurationError("source must be a filesystem path.") from None
    if not path.is_absolute():
        raise ConfigurationError("source must be an absolute regular file, not a symlink.")
    descriptor = None
    try:
        before_open = None
        if _WINDOWS:
            before_open = os.lstat(path)
            if stat.S_ISLNK(before_open.st_mode) or _is_windows_reparse(before_open):
                raise ConfigurationError("source must be an absolute regular file, not a symlink.")
            _validate_regular(before_open)

        descriptor = os.open(path, _read_flags())
        opened = os.fstat(descriptor)
        _validate_regular(opened)
        if _WINDOWS:
            before_identity = _windows_file_identity(before_open)
            opened_identity = _windows_file_identity(opened)
            if before_identity is None or opened_identity is None:
                raise ConfigurationError("Secure secret file identity is unavailable.")
            if before_identity != opened_identity:
                raise ConfigurationError("Secret file changed while it was being opened.")
        value = _read_descriptor(descriptor).decode("utf-8")
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigurationError(f"Unable to read secret file: {exc.__class__.__name__}.") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
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
