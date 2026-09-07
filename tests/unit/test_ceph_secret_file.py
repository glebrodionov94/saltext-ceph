"""Secret keyring files never travel through Salt returns."""

import os
import stat
from types import SimpleNamespace

import pytest

from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph import user_api
from saltext.ceph.utils.ceph.client import APIResponse
from saltext.ceph.utils.ceph.errors import ConfigurationError


def test_secret_file_round_trip_and_overwrite(tmp_path):
    path = tmp_path / "client.keyring"
    assert secret_file.write(path, "first") == str(path)
    assert secret_file.read(path) == "first"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ConfigurationError, match="exists"):
        secret_file.write(path, "second")
    secret_file.write(path, "second", overwrite=True)
    assert secret_file.read(path) == "second"
    assert not list(tmp_path.glob(".client.keyring.*"))


@pytest.mark.parametrize("value", [None, "", "\x00", 42])
def test_invalid_secret_values(tmp_path, value):
    with pytest.raises(ConfigurationError):
        secret_file.write(tmp_path / "secret", value)


def test_secret_paths_must_be_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigurationError):
        secret_file.read("relative.keyring")
    with pytest.raises(ConfigurationError):
        secret_file.write("relative.keyring", "secret")


def test_secret_file_size_limit(tmp_path):
    path = tmp_path / "large.keyring"
    path.write_bytes(b"x" * (secret_file.MAX_SECRET_FILE_SIZE + 1))
    with pytest.raises(ConfigurationError, match="size"):
        secret_file.read(path)


def test_secret_file_rejects_non_regular_files(tmp_path):
    with pytest.raises(ConfigurationError, match="regular file"):
        secret_file.read(tmp_path)


def test_secret_file_rejects_symlinks(tmp_path):
    target = tmp_path / "target"
    target.write_text("secret", encoding="utf-8")
    source = tmp_path / "source"
    try:
        source.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc.__class__.__name__}")
    with pytest.raises(ConfigurationError):
        secret_file.read(source)


@pytest.mark.parametrize("value", [b"", b"contains\x00nul", b"\xff"])
def test_secret_file_rejects_invalid_content(tmp_path, value):
    source = tmp_path / "invalid-secret"
    source.write_bytes(value)
    with pytest.raises(ConfigurationError):
        secret_file.read(source)


def test_secret_file_read_error_does_not_disclose_path(tmp_path):
    source = tmp_path / "sensitive-secret-filename"
    with pytest.raises(ConfigurationError) as exc_info:
        secret_file.read(source)
    message = str(exc_info.value)
    assert str(source) not in message
    assert source.name not in message


def test_posix_read_flags_require_nofollow_and_cloexec(monkeypatch):
    monkeypatch.setattr(secret_file, "_WINDOWS", False)
    monkeypatch.setattr(secret_file.os, "O_NOFOLLOW", 0x10000, raising=False)
    monkeypatch.setattr(secret_file.os, "O_CLOEXEC", 0x20000, raising=False)
    monkeypatch.setattr(secret_file.os, "O_NONBLOCK", 0x40000, raising=False)
    flags = secret_file._read_flags()
    assert flags & secret_file.os.O_NOFOLLOW
    assert flags & secret_file.os.O_CLOEXEC
    assert flags & secret_file.os.O_NONBLOCK


def test_windows_read_flags_use_binary_and_noinherit(monkeypatch):
    monkeypatch.setattr(secret_file, "_WINDOWS", True)
    monkeypatch.setattr(secret_file.os, "O_BINARY", 0x10000, raising=False)
    monkeypatch.setattr(secret_file.os, "O_NOINHERIT", 0x20000, raising=False)
    flags = secret_file._read_flags()
    assert flags & secret_file.os.O_BINARY
    assert flags & secret_file.os.O_NOINHERIT


def test_windows_reparse_point_is_detected(monkeypatch):
    reparse_flag = 0x400
    monkeypatch.setattr(
        secret_file.stat,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        reparse_flag,
        raising=False,
    )
    file_stat = SimpleNamespace(
        st_file_attributes=reparse_flag,
    )
    assert secret_file._is_windows_reparse(file_stat)


def test_windows_read_detects_replacement_and_closes_descriptor(tmp_path, monkeypatch):
    source = tmp_path / "secret"
    before = SimpleNamespace(st_mode=stat.S_IFREG, st_size=6, st_dev=1, st_ino=10)
    opened = SimpleNamespace(st_mode=stat.S_IFREG, st_size=6, st_dev=1, st_ino=11)
    closed = []
    monkeypatch.setattr(secret_file, "_WINDOWS", True)
    monkeypatch.setattr(secret_file.os, "lstat", lambda _path: before)
    monkeypatch.setattr(secret_file.os, "open", lambda _path, _flags: 37)
    monkeypatch.setattr(secret_file.os, "fstat", lambda descriptor: opened)
    monkeypatch.setattr(secret_file.os, "close", closed.append)
    monkeypatch.setattr(
        secret_file.os,
        "read",
        lambda *_args: pytest.fail("a replaced descriptor must not be read"),
    )

    with pytest.raises(ConfigurationError, match="changed"):
        secret_file.read(source)
    assert closed == [37]


def test_windows_read_fails_closed_without_file_identity(tmp_path, monkeypatch):
    source = tmp_path / "secret"
    before = SimpleNamespace(st_mode=stat.S_IFREG, st_size=6, st_dev=0, st_ino=0)
    opened = SimpleNamespace(st_mode=stat.S_IFREG, st_size=6, st_dev=0, st_ino=0)
    closed = []
    monkeypatch.setattr(secret_file, "_WINDOWS", True)
    monkeypatch.setattr(secret_file.os, "lstat", lambda _path: before)
    monkeypatch.setattr(secret_file.os, "open", lambda _path, _flags: 37)
    monkeypatch.setattr(secret_file.os, "fstat", lambda descriptor: opened)
    monkeypatch.setattr(secret_file.os, "close", closed.append)

    with pytest.raises(ConfigurationError, match="identity"):
        secret_file.read(source)
    assert closed == [37]


def test_secret_bytes_are_read_from_the_validated_descriptor(tmp_path, monkeypatch):
    source = tmp_path / "secret"
    opened = SimpleNamespace(st_mode=stat.S_IFREG, st_size=6, st_dev=1, st_ino=10)
    chunks = iter((b"sec", b"ret", b""))
    read_descriptors = []
    closed = []
    monkeypatch.setattr(secret_file, "_WINDOWS", True)
    monkeypatch.setattr(secret_file.os, "lstat", lambda _path: opened)
    monkeypatch.setattr(secret_file.os, "open", lambda _path, _flags: 37)
    monkeypatch.setattr(secret_file.os, "fstat", lambda descriptor: opened)

    def read_chunk(descriptor, _size):
        read_descriptors.append(descriptor)
        return next(chunks)

    monkeypatch.setattr(secret_file.os, "read", read_chunk)
    monkeypatch.setattr(secret_file.os, "close", closed.append)

    assert secret_file.read(source) == "secret"
    assert read_descriptors == [37, 37, 37]
    assert closed == [37]


def test_descriptor_read_enforces_limit_after_fstat(monkeypatch):
    chunks = iter((b"1234", b"5"))
    monkeypatch.setattr(secret_file, "MAX_SECRET_FILE_SIZE", 4)
    monkeypatch.setattr(secret_file.os, "read", lambda _descriptor, _size: next(chunks))
    with pytest.raises(ConfigurationError, match="size"):
        secret_file._read_descriptor(37)


def test_user_api_import_does_not_return_keyring(tmp_path, monkeypatch):
    source = tmp_path / "source.keyring"
    source.write_text("[client.backup]\n key = private-key\n", encoding="utf-8")
    client = type("Client", (), {})()
    imported = []
    monkeypatch.setattr(user_api, "_client", lambda *_args: client)

    def send(_client, keyring):
        imported.append(keyring)
        return APIResponse(201, "Successfully imported user")

    monkeypatch.setattr(user_api.users, "import_keyring", send)
    result = user_api.import_keyring({}, {}, {}, str(source))
    assert imported == ["[client.backup]\n key = private-key\n"]
    assert result == {
        "status": 201,
        "data": {"source": str(source)},
        "headers": {},
    }
    assert "private-key" not in repr(result)


def test_user_api_export_writes_keyring_and_returns_metadata(tmp_path, monkeypatch):
    destination = tmp_path / "export.keyring"
    client = type("Client", (), {})()
    monkeypatch.setattr(user_api, "_client", lambda *_args: client)
    monkeypatch.setattr(
        user_api.users,
        "export_keyring",
        lambda *_args: APIResponse(201, "[client.backup]\n key = private-key\n"),
    )
    result = user_api.export_keyring({}, {}, {}, ["client.backup"], str(destination))
    assert result == {
        "status": 201,
        "data": {"entities": ["client.backup"], "destination": str(destination)},
        "headers": {},
    }
    assert destination.read_text(encoding="utf-8") == "[client.backup]\n key = private-key\n"
    assert "private-key" not in repr(result)
