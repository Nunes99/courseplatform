"""Fail safely when repository files contain secrets absent from the baseline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".secrets.baseline"
BATCH_SIZE = 100
EXCLUDED_FILES = {
    ".bandit-baseline.json",
    ".secrets.baseline",
    "pnpm-lock.yaml",
}


def repository_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value and value.decode("utf-8") not in EXCLUDED_FILES
    ]


def _normalized_path(value: object) -> str:
    return str(value or "").replace("\\", "/").lstrip("./")


def finding_keys(report: dict[str, Any]) -> set[tuple[str, str, str]]:
    findings = set()
    for filename, entries in report.get("results", {}).items():
        for finding in entries:
            findings.add(
                (
                    _normalized_path(filename),
                    str(finding.get("type") or ""),
                    str(finding.get("hashed_secret") or ""),
                )
            )
    return findings


def new_findings(
    baseline: dict[str, Any], reports: list[dict[str, Any]]
) -> list[tuple[str, str, int]]:
    reviewed = finding_keys(baseline)
    detected: dict[tuple[str, str, str], int] = {}
    for report in reports:
        for filename, entries in report.get("results", {}).items():
            for finding in entries:
                key = (
                    _normalized_path(filename),
                    str(finding.get("type") or ""),
                    str(finding.get("hashed_secret") or ""),
                )
                detected[key] = int(finding.get("line_number") or 0)
    return sorted(
        (filename, finding_type, detected[key])
        for key in detected.keys() - reviewed
        for filename, finding_type, _ in (key,)
    )


def _scan(files: list[str]) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "detect_secrets",
        "scan",
        "--all-files",
        *files,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    if not BASELINE.is_file():
        print("Secret baseline is missing.", file=sys.stderr)
        return 2
    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Secret baseline is invalid: {type(exc).__name__}.", file=sys.stderr)
        return 2
    files = repository_files()
    try:
        reports = [
            _scan(files[offset : offset + BATCH_SIZE])
            for offset in range(0, len(files), BATCH_SIZE)
        ]
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"Secret scan failed safely: {type(exc).__name__}.", file=sys.stderr)
        return 2
    unreviewed = new_findings(baseline, reports)
    if unreviewed:
        print(
            f"Potential secret detected in {len(unreviewed)} location(s) "
            "outside the reviewed baseline:",
            file=sys.stderr,
        )
        for filename, finding_type, line_number in unreviewed:
            print(f"- {finding_type} {filename}:{line_number}", file=sys.stderr)
        return 1
    print(f"Secret baseline verified across {len(files)} repository files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
