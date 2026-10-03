import json
import re
import unittest
from datetime import date
from pathlib import Path

from scripts import check_bandit_baseline, check_recovery_readiness


ROOT = Path(__file__).resolve().parents[1]


class Stage14SecurityTests(unittest.TestCase):
    def test_recovery_schedule_reports_ready_and_overdue(self):
        ready = check_recovery_readiness.evaluate_drill_schedule(
            date(2026, 10, 3), 90, date(2026, 12, 31)
        )
        overdue = check_recovery_readiness.evaluate_drill_schedule(
            date(2026, 10, 3), 90, date(2027, 1, 2)
        )
        self.assertFalse(ready["overdue"])
        self.assertTrue(overdue["overdue"])

    def test_repository_recovery_evidence_is_current(self):
        report = check_recovery_readiness.inspect_repository(date(2026, 10, 3))
        self.assertEqual("ready", report["status"])
        self.assertTrue(report["requiresExternalDrill"])

    def test_security_workflows_do_not_receive_runtime_secrets(self):
        workflow_text = "\n".join(
            (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            for name in ("security.yml", "codeql.yml", "recovery-readiness.yml")
        ).lower()
        forbidden = (
            "database_url",
            "supabase_secret_key",
            "service_role",
            "job_runner_secret",
            "smtp_password",
        )
        for value in forbidden:
            self.assertNotIn(value, workflow_text)

    def test_security_workflow_removes_bandit_report_before_secret_scan(self):
        workflow_text = (
            ROOT / ".github" / "workflows" / "security.yml"
        ).read_text(encoding="utf-8")
        cleanup = workflow_text.index("rm -f bandit-current.json")
        secret_scan = workflow_text.index("python scripts/check_secrets.py")
        self.assertLess(cleanup, secret_scan)

    def test_dependency_manifests_and_secret_baseline_are_versioned(self):
        self.assertTrue((ROOT / ".github" / "dependabot.yml").is_file())
        lockfile = (ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(lockfile, re.compile(r"https?://[^/\s]+:[^/\s]+@"))
        baseline = json.loads((ROOT / ".secrets.baseline").read_text(encoding="utf-8"))
        self.assertIn("plugins_used", baseline)
        self.assertIn("results", baseline)

        bandit = json.loads(
            (ROOT / ".bandit-baseline.json").read_text(encoding="utf-8")
        )
        high_severity = [
            finding
            for finding in bandit.get("results", [])
            if finding.get("issue_severity") == "HIGH"
        ]
        self.assertEqual([], high_severity)

    def test_bandit_baseline_normalizes_paths_between_windows_and_linux(self):
        baseline = {
            "results": [
                {
                    "test_id": "B310",
                    "filename": "backend\\courseplatform\\files.py",
                    "line_number": 42,
                    "issue_severity": "MEDIUM",
                    "issue_confidence": "HIGH",
                }
            ]
        }
        current = {
            "results": [
                {
                    "test_id": "B310",
                    "filename": "backend/courseplatform/files.py",
                    "line_number": 42,
                    "issue_severity": "MEDIUM",
                    "issue_confidence": "HIGH",
                }
            ]
        }
        self.assertEqual([], check_bandit_baseline.compare_reports(baseline, current))

    def test_bandit_baseline_rejects_a_new_relevant_finding(self):
        baseline = {"results": []}
        current = {
            "results": [
                {
                    "test_id": "B608",
                    "filename": "backend/courseplatform/query.py",
                    "line_number": 7,
                    "issue_severity": "HIGH",
                    "issue_confidence": "MEDIUM",
                }
            ]
        }
        findings = check_bandit_baseline.compare_reports(baseline, current)
        self.assertEqual(1, len(findings))


if __name__ == "__main__":
    unittest.main()
