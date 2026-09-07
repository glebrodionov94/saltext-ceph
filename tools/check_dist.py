"""Validate release archives before they are uploaded to a package index."""

import argparse
import configparser
import email.policy
import re
import tarfile
import zipfile
from email.message import Message
from pathlib import Path
from pathlib import PurePosixPath

from packaging.requirements import InvalidRequirement
from packaging.requirements import Requirement
from packaging.specifiers import InvalidSpecifier
from packaging.specifiers import SpecifierSet
from packaging.version import Version

try:
    from tools.check_secrets import PATTERNS
except ModuleNotFoundError:  # Direct ``python tools/check_dist.py`` invocation.
    from check_secrets import PATTERNS

PROJECT_NAME = "saltext.ceph"
PACKAGE_PREFIX = "saltext/ceph/"
SOURCE_PACKAGE = Path("src/saltext/ceph")


def _single(paths, description):
    matches = list(paths)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {description}, found {len(matches)}")
    return matches[0]


def _canonical_name(value):
    return re.sub(r"[-_.]+", "-", value).lower()


def _metadata(raw):
    return email.message_from_bytes(raw, policy=email.policy.default)


def _validate_metadata(metadata: Message, expected_version=None):
    name = metadata.get("Name", "")
    version = metadata.get("Version", "")
    if _canonical_name(name) != _canonical_name(PROJECT_NAME):
        raise RuntimeError(f"Unexpected distribution name: {name!r}")
    if not version:
        raise RuntimeError("Distribution metadata has no version")
    if expected_version is not None and version != expected_version:
        raise RuntimeError(f"Expected version {expected_version!r}, found {version!r}")
    if metadata.get("License-Expression") != "Apache-2.0":
        raise RuntimeError("Distribution does not declare the Apache-2.0 SPDX license")

    requirement_names = set()
    for value in metadata.get_all("Requires-Dist", []):
        try:
            requirement_names.add(_canonical_name(Requirement(value).name))
        except InvalidRequirement as exc:
            raise RuntimeError(f"Invalid Requires-Dist metadata: {value!r}") from exc
    for required_name in ("requests", "salt"):
        if required_name not in requirement_names:
            raise RuntimeError(f"Distribution metadata does not require {required_name}")

    requires_python = metadata.get("Requires-Python", "")
    try:
        python_specifier = SpecifierSet(requires_python)
    except InvalidSpecifier as exc:
        raise RuntimeError(f"Invalid Requires-Python metadata: {requires_python!r}") from exc
    if (
        Version("3.9") in python_specifier
        or Version("3.10") not in python_specifier
        or Version("3.14") not in python_specifier
    ):
        raise RuntimeError("Distribution must support Python 3.10 through 3.14")

    project_urls = {
        key.strip(): value.strip()
        for field in metadata.get_all("Project-URL", [])
        for key, separator, value in (field.partition(","),)
        if separator
    }
    for required_url in ("Source", "Tracker"):
        if not project_urls.get(required_url, "").startswith("https://github.com/"):
            raise RuntimeError(f"Distribution has no GitHub {required_url} project URL")
    return version


def _validate_member_names(names):
    for name in names:
        path = PurePosixPath(name)
        lowered = name.lower()
        lowered_parts = {part.lower() for part in path.parts}
        basename = path.name.lower()
        if (
            not name
            or "\\" in name
            or "\0" in name
            or path.is_absolute()
            or ".." in path.parts
            or re.match(r"^[a-z]:", lowered)
        ):
            raise RuntimeError(f"Unsafe distribution member path: {name}")
        if (
            basename == ".env"
            or basename.startswith(".env.")
            or basename in {".netrc", ".pypirc", "openapi.json"}
            or basename.endswith((".jks", ".key", ".p12", ".pem", ".pfx"))
            or "__pycache__" in lowered_parts
            or lowered.endswith((".pyc", ".pyo"))
        ):
            raise RuntimeError(f"Forbidden file in distribution: {name}")


def _validate_member_contents(name, content):
    """Reject credential material without copying it into build logs."""
    for label, pattern in PATTERNS.items():
        if pattern.search(content):
            raise RuntimeError(f"Possible {label} in distribution member {name}; value suppressed")


def _source_python_files():
    if not SOURCE_PACKAGE.is_dir():
        raise RuntimeError(f"Source package is missing: {SOURCE_PACKAGE}")
    return {
        f"{PACKAGE_PREFIX}{path.relative_to(SOURCE_PACKAGE).as_posix()}"
        for path in SOURCE_PACKAGE.rglob("*.py")
    }


def _check_wheel(path, expected_version=None):
    if not path.name.endswith("-py3-none-any.whl"):
        raise RuntimeError(f"Wheel is not tagged as pure Python 3: {path.name}")

    with zipfile.ZipFile(path) as archive:
        archive_names = archive.namelist()
        names = set(archive_names)
        if len(names) != len(archive_names):
            raise RuntimeError("Wheel contains duplicate member names")
        _validate_member_names(names)
        for name in names:
            _validate_member_contents(name, archive.read(name))
        metadata_path = _single(
            (name for name in names if name.endswith(".dist-info/METADATA")),
            "wheel METADATA file",
        )
        metadata = _metadata(archive.read(metadata_path))
        version = _validate_metadata(metadata, expected_version)

        entry_points_path = _single(
            (name for name in names if name.endswith(".dist-info/entry_points.txt")),
            "wheel entry_points.txt file",
        )
        entry_points = configparser.ConfigParser()
        entry_points.read_string(archive.read(entry_points_path).decode("utf-8"))
        if entry_points.get("salt.loader", PROJECT_NAME, fallback="") != "saltext.ceph":
            raise RuntimeError("Wheel does not contain the saltext.ceph Salt loader entry point")

        for license_name in ("LICENSE", "NOTICE"):
            if not any(name.endswith(f".dist-info/licenses/{license_name}") for name in names):
                raise RuntimeError(f"Wheel does not contain {license_name}")

        expected_python = _source_python_files()
        expected_python.add(f"{PACKAGE_PREFIX}version.py")
        missing = sorted(expected_python.difference(names))
        if missing:
            raise RuntimeError(f"Python files missing from wheel: {', '.join(missing)}")
    return version


def _check_sdist(path, expected_version=None):
    with tarfile.open(path, "r:gz") as archive:
        archive_members = archive.getmembers()
        _validate_member_names(member.name for member in archive_members)
        unsupported = [
            member.name for member in archive_members if not (member.isfile() or member.isdir())
        ]
        if unsupported:
            raise RuntimeError(
                f"Source distribution contains links or special files: {', '.join(unsupported)}"
            )
        file_members = [member for member in archive_members if member.isfile()]
        members = {member.name: member for member in file_members}
        if len(members) != len(file_members):
            raise RuntimeError("Source distribution contains duplicate member names")
        names = set(members)
        for name, member in members.items():
            member_file = archive.extractfile(member)
            if member_file is None:
                raise RuntimeError(f"Could not read source distribution member {name}")
            _validate_member_contents(name, member_file.read())
        roots = {PurePosixPath(name).parts[0] for name in names}
        root = _single(roots, "sdist root directory")

        metadata_path = f"{root}/PKG-INFO"
        if metadata_path not in names:
            raise RuntimeError("Source distribution does not contain PKG-INFO")
        metadata_file = archive.extractfile(metadata_path)
        if metadata_file is None:
            raise RuntimeError("Could not read PKG-INFO from source distribution")
        version = _validate_metadata(_metadata(metadata_file.read()), expected_version)

        for relative in (
            "LICENSE",
            "NOTICE",
            "README.md",
            "CHANGELOG.md",
            "SECURITY.md",
            "pyproject.toml",
        ):
            if f"{root}/{relative}" not in names:
                raise RuntimeError(f"Source distribution does not contain {relative}")

        expected_python = {f"{root}/src/{relative}" for relative in _source_python_files()}
        expected_python.add(f"{root}/src/{PACKAGE_PREFIX}version.py")
        missing = sorted(expected_python.difference(names))
        if missing:
            raise RuntimeError(f"Python files missing from sdist: {', '.join(missing)}")
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="Directory containing one wheel and one sdist")
    parser.add_argument("--expected-version", help="Require this exact Core Metadata version")
    args = parser.parse_args()

    wheel = _single(args.dist.glob("*.whl"), "wheel")
    sdist = _single(args.dist.glob("*.tar.gz"), "source distribution")
    wheel_version = _check_wheel(wheel, args.expected_version)
    sdist_version = _check_sdist(sdist, args.expected_version)
    if wheel_version != sdist_version:
        raise RuntimeError(
            f"Wheel version {wheel_version!r} differs from sdist version {sdist_version!r}"
        )
    print(f"Validated {wheel.name} and {sdist.name} as {PROJECT_NAME} {wheel_version}")


if __name__ == "__main__":
    main()
