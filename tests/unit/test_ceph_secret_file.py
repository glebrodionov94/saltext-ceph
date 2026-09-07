"""Secret keyring files never travel through Salt returns."""

import os

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
