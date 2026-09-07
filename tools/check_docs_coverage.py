"""Validate the report produced by the Sphinx coverage builder."""

import argparse
import re
from pathlib import Path

_TOTAL_ROW = re.compile(r"^\|\s*TOTAL\s*\|[^|]*\|\s*(\d+)\s*\|\s*$", re.MULTILINE)
_IMPORT_FAILURE_HEADING = "Modules that failed to import"


def check_report(path):
    """Raise ``RuntimeError`` when a Python object is missing from the docs."""
    try:
        report = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Sphinx coverage report is missing: {path}") from exc

    totals = _TOTAL_ROW.findall(report)
    if len(totals) != 1:
        raise RuntimeError(f"Sphinx coverage report has no unambiguous TOTAL row: {path}")

    undocumented = int(totals[0])
    import_failures = _IMPORT_FAILURE_HEADING in report
    if undocumented or import_failures:
        problems = []
        if undocumented:
            problems.append(f"{undocumented} undocumented Python object(s)")
        if import_failures:
            problems.append("one or more modules failed to import")
        raise RuntimeError(f"Sphinx coverage failed ({', '.join(problems)}):\n{report.rstrip()}")


def main(argv=None):
    """Run the command-line report check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Path to Sphinx's coverage/python.txt")
    args = parser.parse_args(argv)
    try:
        check_report(args.report)
    except RuntimeError as exc:
        parser.error(str(exc))
    print(f"Sphinx Python API coverage is complete: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
