"""Tests for the Sphinx Python API coverage guard."""

import pytest

from tools import check_docs_coverage


def _write_report(path, undocumented="0", details=""):
    path.write_text(
        "\n".join(
            (
                "Undocumented Python objects",
                "===========================",
                "",
                "Statistics",
                "----------",
                "",
                "+--------+----------+--------------+",
                "| Module | Coverage | Undocumented |",
                "+========+==========+==============+",
                f"| TOTAL  | 100      | {undocumented:<12} |",
                "+--------+----------+--------------+",
                "",
                details,
            )
        ),
        encoding="utf-8",
    )


def test_complete_report_passes(tmp_path):
    report = tmp_path / "python.txt"
    _write_report(report)

    assert check_docs_coverage.check_report(report) is None


def test_undocumented_objects_fail_with_report_details(tmp_path):
    report = tmp_path / "python.txt"
    _write_report(report, undocumented="1", details="saltext.ceph.modules.ceph_host\n * list_")

    with pytest.raises(RuntimeError, match="1 undocumented Python object") as exc_info:
        check_docs_coverage.check_report(report)

    assert "ceph_host" in str(exc_info.value)


def test_missing_or_malformed_report_fails_closed(tmp_path):
    missing = tmp_path / "missing.txt"
    with pytest.raises(RuntimeError, match="report is missing"):
        check_docs_coverage.check_report(missing)

    malformed = tmp_path / "python.txt"
    malformed.write_text("not a Sphinx coverage report", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no unambiguous TOTAL row"):
        check_docs_coverage.check_report(malformed)


def test_module_import_failures_fail_even_at_full_object_coverage(tmp_path):
    report = tmp_path / "python.txt"
    _write_report(report, details="Modules that failed to import\n-----------------------------")

    with pytest.raises(RuntimeError, match="modules failed to import"):
        check_docs_coverage.check_report(report)
