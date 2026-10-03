"""Compare a Bandit JSON report with the reviewed cross-platform baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


RELEVANT_LEVELS = {"MEDIUM", "HIGH"}


def _normalized_path(value: object) -> str:
    return str(value or "").replace("\\", "/").lstrip("./")


def finding_key(finding: dict[str, Any]) -> tuple[str, str, int, str, str]:
    """Return a stable key without retaining source text or other sensitive data."""
    return (
        str(finding.get("test_id") or ""),
        _normalized_path(finding.get("filename")),
        int(finding.get("line_number") or 0),
        str(finding.get("issue_severity") or "").upper(),
        str(finding.get("issue_confidence") or "").upper(),
    )


def relevant_findings(report: dict[str, Any]) -> set[tuple[str, str, int, str, str]]:
    findings = set()
    for finding in report.get("results", []):
        severity = str(finding.get("issue_severity") or "").upper()
        confidence = str(finding.get("issue_confidence") or "").upper()
        if severity in RELEVANT_LEVELS and confidence in RELEVANT_LEVELS:
            findings.add(finding_key(finding))
    return findings


def compare_reports(
    baseline: dict[str, Any], current: dict[str, Any]
) -> list[tuple[str, str, int, str, str]]:
    return sorted(relevant_findings(current) - relevant_findings(baseline))


def _load_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Relatorio Bandit invalido: {path}: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(report.get("results"), list):
        raise SystemExit(f"Relatorio Bandit sem uma lista de resultados: {path}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, help="Relatorio JSON produzido pelo Bandit")
    parser.add_argument(
        "--baseline", type=Path, default=Path(".bandit-baseline.json")
    )
    args = parser.parse_args()

    baseline = _load_report(args.baseline)
    current = _load_report(args.report)
    new_findings = compare_reports(baseline, current)
    if new_findings:
        print(f"Bandit encontrou {len(new_findings)} ocorrencia(s) nova(s):")
        for test_id, filename, line, severity, confidence in new_findings:
            print(f"- {severity}/{confidence} {test_id} {filename}:{line}")
        return 1

    reviewed = len(relevant_findings(current))
    print(f"Bandit: nenhuma ocorrencia nova; {reviewed} ocorrencia(s) revista(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
