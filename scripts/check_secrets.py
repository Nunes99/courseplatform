"""Fail safely when repository files contain secrets absent from the baseline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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


def main() -> int:
    if not BASELINE.is_file():
        print("Secret baseline is missing.", file=sys.stderr)
        return 2
    files = repository_files()
    for offset in range(0, len(files), BATCH_SIZE):
        command = [
            sys.executable,
            "-m",
            "detect_secrets.pre_commit_hook",
            "--baseline",
            str(BASELINE),
            *files[offset : offset + BATCH_SIZE],
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            print(
                "Potential secret detected outside the reviewed baseline. "
                "Run detect-secrets locally and review the finding without "
                "copying its value into logs.",
                file=sys.stderr,
            )
            return 1
    print(f"Secret baseline verified across {len(files)} repository files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
