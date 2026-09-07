"""Reject common long-lived credentials without printing their values."""

import re
import sys
from pathlib import Path

PATTERNS = {
    "AWS access key": re.compile(rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    "GitHub token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})"),
    "private key": re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    "PyPI token": re.compile(rb"pypi-[A-Za-z0-9_-]{40,}"),
}


def scan_file(path):
    """Return credential labels and line numbers, without returning matched bytes."""
    try:
        content = Path(path).read_bytes()
    except OSError as exc:
        return [(f"could not read file: {type(exc).__name__}", 0)]
    findings = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        findings.extend(
            (label, line_number) for label, pattern in PATTERNS.items() if pattern.search(line)
        )
    return findings


def main(arguments=None):
    """Scan pre-commit filenames and return a non-zero status on a match."""
    failed = False
    for filename in arguments if arguments is not None else sys.argv[1:]:
        for label, line_number in scan_file(filename):
            failed = True
            location = f"{filename}:{line_number}" if line_number else filename
            print(f"{location}: possible {label}; value suppressed")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
