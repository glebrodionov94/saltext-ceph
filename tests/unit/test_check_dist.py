"""Tests for release archive validation."""

import email
import io
import tarfile
import zipfile

import pytest

from tools import check_dist


def _metadata(**replacements):
    values = {
        "name": "saltext.ceph",
        "version": "1.2.3",
        "license": "Apache-2.0",
        "python": ">=3.10",
        "salt": "salt>=3006",
        "requests": "requests>=2.32.4,<3",
    }
    values.update(replacements)
    return email.message_from_string(
        "\n".join(
            (
                "Metadata-Version: 2.4",
                f"Name: {values['name']}",
                f"Version: {values['version']}",
                f"License-Expression: {values['license']}",
                f"Requires-Python: {values['python']}",
                f"Requires-Dist: {values['salt']}",
                f"Requires-Dist: {values['requests']}",
                "Project-URL: Source, https://github.com/glebrodionov94/saltext-ceph",
                "Project-URL: Tracker, https://github.com/glebrodionov94/saltext-ceph/issues",
                "",
            )
        )
    )


def test_release_metadata_contract():
    assert check_dist._validate_metadata(_metadata(), "1.2.3") == "1.2.3"


@pytest.mark.parametrize(
    ("replacement", "message"),
    (
        ({"salt": "salt-fake>=1"}, "does not require salt"),
        ({"requests": "requests-fake>=1"}, "does not require requests"),
        ({"python": ">=3.11"}, "Python 3.10 through 3.14"),
        ({"python": ">=3.9"}, "Python 3.10 through 3.14"),
    ),
)
def test_release_metadata_rejects_incompatible_dependencies(replacement, message):
    with pytest.raises(RuntimeError, match=message):
        check_dist._validate_metadata(_metadata(**replacement))


@pytest.mark.parametrize(
    "name",
    (
        "../credentials",
        "/absolute/member",
        "C:/absolute/member",
        "package\\..\\credentials",
        "package/.env.production",
        "package/.pypirc",
        "package/openapi.json",
        "package/private-key.pem",
        "package/__PYCACHE__/module.py",
    ),
)
def test_distribution_rejects_unsafe_member_names(name):
    with pytest.raises(RuntimeError):
        check_dist._validate_member_names([name])


def test_distribution_scans_binary_members_without_disclosing_secret():
    token = b"pypi-" + b"A" * 48

    with pytest.raises(RuntimeError) as exc_info:
        check_dist._validate_member_contents("payload.bin", b"\0" + token)

    assert "Possible PyPI token" in str(exc_info.value)
    assert token.decode() not in str(exc_info.value)


def test_wheel_rejects_duplicate_members(tmp_path):
    wheel = tmp_path / "saltext_ceph-1.2.3-py3-none-any.whl"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("duplicate", b"first")
            archive.writestr("duplicate", b"second")

    with pytest.raises(RuntimeError, match="duplicate member"):
        check_dist._check_wheel(wheel)


def test_sdist_rejects_links(tmp_path):
    sdist = tmp_path / "saltext_ceph-1.2.3.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        root = tarfile.TarInfo("saltext_ceph-1.2.3")
        root.type = tarfile.DIRTYPE
        archive.addfile(root)
        regular = tarfile.TarInfo("saltext_ceph-1.2.3/README.md")
        payload = b"safe"
        regular.size = len(payload)
        archive.addfile(regular, io.BytesIO(payload))
        link = tarfile.TarInfo("saltext_ceph-1.2.3/linked")
        link.type = tarfile.SYMTYPE
        link.linkname = "README.md"
        archive.addfile(link)

    with pytest.raises(RuntimeError, match="links or special files"):
        check_dist._check_sdist(sdist)
