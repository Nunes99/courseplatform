import json
import logging
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient

from backend.courseplatform import jobs
from backend.courseplatform.app import app
from backend.courseplatform.observability import JsonFormatter


ROOT = Path(__file__).resolve().parents[1]


class _Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, result):
        self.result = result
        self.queries = []
        self.committed = False

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()).lower(), params))
        return self.result

    def commit(self):
        self.committed = True


def _connection_for(conn):
    @contextmanager
    def fake_connection():
        yield conn

    return fake_connection


class DurableJobTests(unittest.TestCase):
    def test_enqueue_encrypts_payload_and_is_idempotent(self):
        conn = _Connection(_Result(row={"job_id": "JOB-1"}))
        settings = SimpleNamespace(
            notification_config_encryption_key="test-only-encryption-key-with-32-bytes",
            default_organization_id="ORG-A",
        )
        with (
            patch.object(jobs, "connection", _connection_for(conn)),
            patch.object(jobs, "get_settings", return_value=settings),
            patch.object(jobs, "_job_id", return_value="JOB-1"),
        ):
            job_id = jobs.enqueue_identity_delivery(
                jobs.PASSWORD_RESET_JOB,
                {"resetId": "PWR-1", "token": "one-time-secret"},
            )

        query, params = conn.queries[0]
        self.assertEqual("JOB-1", job_id)
        self.assertIn("pgp_sym_encrypt", query)
        self.assertIn("on conflict (organization_id, idempotency_key)", query)
        self.assertEqual("ORG-A", params[1])
        self.assertEqual(f"{jobs.PASSWORD_RESET_JOB}:PWR-1", params[3])
        self.assertNotIn("one-time-secret", query)
        self.assertTrue(conn.committed)

    def test_terminal_failure_records_dead_letter_timestamp(self):
        conn = _Connection(_Result())
        with patch.object(jobs, "connection", _connection_for(conn)):
            status = jobs._mark_failed(
                {"job_id": "JOB-1", "attempt_count": 5, "max_attempts": 5},
                "worker-a",
                RuntimeError("provider down"),
            )
        query, params = conn.queries[0]
        self.assertEqual("DEAD", status)
        self.assertIn("dead_lettered_at", query)
        self.assertEqual("DEAD", params[5])
        self.assertTrue(conn.committed)

    def test_claimed_job_keeps_organization_context(self):
        conn = _Connection(_Result(rows=[{
            "job_id": "JOB-1",
            "organization_id": "ORG-B",
            "job_type": jobs.PASSWORD_RESET_JOB,
            "attempt_count": 1,
            "max_attempts": 5,
            "payload_json": '{"resetId":"PWR-1","token":"secret"}',
        }]))
        settings = SimpleNamespace(
            notification_config_encryption_key="test-only-encryption-key-with-32-bytes",
        )
        with (
            patch.object(jobs, "connection", _connection_for(conn)),
            patch.object(jobs, "get_settings", return_value=settings),
        ):
            claimed = jobs.claim_jobs("worker-a", 10)
        self.assertEqual("ORG-B", claimed[0]["organization_id"])
        self.assertIn("organization_id", conn.queries[0][0])

    def test_retry_cycle_does_not_log_plaintext_payload(self):
        claimed = [{
            "job_id": "JOB-1",
            "job_type": jobs.PASSWORD_RESET_JOB,
            "attempt_count": 1,
            "max_attempts": 5,
            "payload": {"resetId": "PWR-1", "token": "one-time-secret"},
        }]
        settings = SimpleNamespace(job_batch_size=20)
        channel_result = {"sent": 0, "failed": 0, "pending": 0}
        with (
            patch.object(jobs, "get_settings", return_value=settings),
            patch.object(jobs, "claim_jobs", return_value=claimed),
            patch.object(jobs, "_execute_job", side_effect=RuntimeError("provider down")),
            patch.object(jobs, "_mark_failed", return_value="PENDING"),
            patch.object(jobs, "operational_metrics", return_value={
                "pendingJobs": 1,
                "processingJobs": 0,
                "deadJobs": 0,
                "overdueJobs": 0,
                "failedNotifications": 0,
            }),
            patch("backend.courseplatform.actions.deliver_pending_whatsapp", return_value=channel_result),
            patch("backend.courseplatform.actions.deliver_pending_email", return_value=channel_result),
            patch("backend.courseplatform.actions.deliver_pending_telegram", return_value=channel_result),
            patch("backend.courseplatform.actions.deliver_pending_push", return_value=channel_result),
            self.assertLogs("backend.courseplatform.jobs", level="WARNING") as captured,
        ):
            result = jobs.run_operational_cycle(worker_id="test-worker")

        self.assertEqual(1, result["retried"])
        self.assertNotIn("one-time-secret", " ".join(captured.output))

    def test_runner_secret_accepts_bearer_or_explicit_header(self):
        settings = SimpleNamespace(job_runner_secret="runner-secret")
        with patch.object(jobs, "get_settings", return_value=settings):
            self.assertTrue(jobs.runner_authorized("Bearer runner-secret", ""))
            self.assertTrue(jobs.runner_authorized("", "runner-secret"))
            self.assertFalse(jobs.runner_authorized("Bearer wrong", ""))

    def test_operational_alert_fingerprint_is_deterministic(self):
        first = jobs._alert_fingerprint({
            "deadJobs": 2, "overdueJobs": 1, "failedNotifications": 3,
            "pendingJobs": 99,
        })
        second = jobs._alert_fingerprint({
            "failedNotifications": 3, "overdueJobs": 1, "deadJobs": 2,
        })
        self.assertEqual(first, second)

    def test_operational_alert_includes_database_saturation(self):
        settings = SimpleNamespace(db_connection_alert_percent=80)
        with patch.object(jobs, "get_settings", return_value=settings):
            self.assertFalse(jobs._operational_alert_triggered({
                "deadJobs": 0,
                "overdueJobs": 0,
                "failedNotifications": 0,
                "dbConnectionUtilizationPercent": 79,
            }))
            self.assertTrue(jobs._operational_alert_triggered({
                "deadJobs": 0,
                "overdueJobs": 0,
                "failedNotifications": 0,
                "dbConnectionUtilizationPercent": 80,
            }))

    def test_operational_alert_targets_active_owner_via_configured_email(self):
        conn = _Connection(_Result(rows=[{
            "email": "owner@example.test",
            "full_name": "Platform Owner",
        }]))
        configuration = {"configured": True}
        send = Mock(return_value="message-id")
        settings = SimpleNamespace(platform_url="https://example.test")
        with (
            patch.object(jobs, "_claim_operational_alert", return_value=True),
            patch.object(jobs, "connection", _connection_for(conn)),
            patch.object(jobs, "_finish_operational_alert") as finish,
            patch.object(jobs, "get_settings", return_value=settings),
            patch("backend.courseplatform.actions.email_runtime_configuration", return_value=configuration),
            patch("backend.courseplatform.actions.send_email_notification", send),
        ):
            jobs._dispatch_operational_alert({
                "deadJobs": 1,
                "overdueJobs": 0,
                "failedNotifications": 0,
            })

        delivery = send.call_args.args[0]
        self.assertEqual("owner@example.test", delivery["recipient"])
        self.assertEqual("https://example.test/admin.html#/operations", delivery["action_url"])
        self.assertNotIn("owner@example.test", delivery["message"])
        finish.assert_called_once_with()


class ObservabilityTests(unittest.TestCase):
    client = TestClient(app)

    def test_request_id_is_returned_and_public_runner_is_denied(self):
        response = self.client.post(
            "/api/internal/jobs/run",
            headers={"x-request-id": "request-stage13-1"},
        )
        self.assertEqual(401, response.status_code)
        self.assertEqual("request-stage13-1", response.headers["x-request-id"])
        self.assertNotIn("JOB_RUNNER_SECRET", response.text)

    def test_json_formatter_contains_safe_operational_fields(self):
        record = logging.LogRecord(
            "courseplatform.test", logging.INFO, __file__, 1,
            "Completed", (), None,
        )
        record.event = "test_completed"
        record.request_id = "req-1"
        record.duration_ms = 14
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual("test_completed", payload["event"])
        self.assertEqual("req-1", payload["request_id"])
        self.assertEqual(14, payload["duration_ms"])


class Stage13MigrationTests(unittest.TestCase):
    def test_operational_queue_is_private_and_versioned(self):
        migration = (
            ROOT / "supabase" / "migrations" /
            "20261001120000_add_durable_operational_jobs.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("create table if not exists courseplatform.operational_jobs", migration)
        self.assertIn("payload_encrypted bytea", migration)
        self.assertIn("add column if not exists claim_token", migration)
        self.assertIn("add column if not exists available_at", migration)
        self.assertIn("enable row level security", migration)
        self.assertIn("from public, anon, authenticated", migration)
        self.assertIn("for update", (ROOT / "backend" / "courseplatform" / "jobs.py").read_text(encoding="utf-8").lower())
        self.assertIn("20261001120000", migration)

    def test_scheduler_uses_vault_and_contains_no_secret_value(self):
        migration = (
            ROOT / "supabase" / "migrations" /
            "20261003120000_schedule_operational_worker.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("create extension if not exists pg_cron", migration)
        self.assertIn("create extension if not exists pg_net", migration)
        self.assertIn("vault.decrypted_secrets", migration)
        self.assertIn("authorization", migration)
        self.assertIn("/api/internal/jobs/run", migration)
        self.assertNotIn("job_runner_secret=", migration)

    def test_operational_alert_state_is_private_and_versioned(self):
        migration = (
            ROOT / "supabase" / "migrations" /
            "20261003060000_add_operational_alert_delivery.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("create table if not exists courseplatform.operational_alert_state", migration)
        self.assertIn("enable row level security", migration)
        self.assertIn("from public, anon, authenticated", migration)
        self.assertIn("20261003060000", migration)

    def test_operational_jobs_are_isolated_and_deduplicated_per_organization(self):
        migration = (
            ROOT / "supabase" / "migrations" /
            "20261005020000_isolate_operational_jobs_by_organization.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("add column if not exists organization_id", migration)
        self.assertIn("foreign key (organization_id)", migration)
        self.assertIn("on delete restrict not valid", migration)
        self.assertIn(
            "operational_jobs(organization_id, idempotency_key)", migration
        )
        self.assertIn("dead_lettered_at", migration)
        self.assertIn("20261005020000", migration)

    def test_m3_rollout_requires_explicit_apply_and_has_postflight(self):
        source = (
            ROOT / "scripts" / "apply_m3_operational_isolation_migration.py"
        ).read_text(encoding="utf-8").lower()
        self.assertIn('mode.add_argument("--apply"', source)
        self.assertIn('mode.add_argument("--postflight"', source)
        self.assertIn("mode=preflight_only", source)
        self.assertIn("jobs_requiring_organization_backfill", source)
        self.assertIn("postflight_foreign_key_validated", source)
        self.assertIn("postflight_tenant_unique_index", source)
        self.assertIn("postflight_duplicate_keys", source)

    def test_operational_metrics_include_tenant_breakdown(self):
        source = (ROOT / "backend" / "courseplatform" / "jobs.py").read_text(
            encoding="utf-8"
        ).lower()
        self.assertIn("group by organization_id", source)
        self.assertIn('"organizations"', source)


if __name__ == "__main__":
    unittest.main()
