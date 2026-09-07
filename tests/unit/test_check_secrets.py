"""Tests for the repository credential guard."""

from tools import check_secrets


def test_detects_tokens_without_returning_the_value(tmp_path):
    token = "pypi-" + "A" * 48
    candidate = tmp_path / "config.txt"
    candidate.write_text(f"safe=true\ntoken={token}\n", encoding="utf-8")

    assert check_secrets.scan_file(candidate) == [("PyPI token", 2)]


def test_main_suppresses_the_detected_value(tmp_path, capsys):
    token = "github_pat_" + "B" * 60
    candidate = tmp_path / "config.txt"
    candidate.write_text(token, encoding="utf-8")

    assert check_secrets.main([str(candidate)]) == 1
    output = capsys.readouterr().out
    assert "possible GitHub token" in output
    assert token not in output


def test_scans_binary_files_and_ignores_documentation_names(tmp_path):
    binary = tmp_path / "data.bin"
    binary.write_bytes(b"pypi-" + b"C" * 48 + b"\0")
    documentation = tmp_path / "workflow.txt"
    documentation.write_text("pypa/gh-action-pypi-publish", encoding="utf-8")

    assert check_secrets.scan_file(binary) == [("PyPI token", 1)]
    assert not check_secrets.scan_file(documentation)
    assert check_secrets.main([str(documentation)]) == 0
