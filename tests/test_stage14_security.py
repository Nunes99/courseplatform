import json
import re
import unittest
from datetime import date
from pathlib import Path

from scripts import check_recovery_readiness


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


if __name__ == "__main__":
    unittest.main()
