import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import monitor_production


def _response(path, status=200, duration=120, metrics_percent=12):
    if path == "/health/live":
        body = b'{"status":"ok"}'
        content_type = "application/json"
    elif path == "/health/ready":
        body = b'{"status":"ready"}'
        content_type = "application/json"
    elif path == "/health/metrics":
        body = json.dumps({
            "status": "ok",
            "metrics": {
                "dbConnectionUtilizationPercent": metrics_percent,
                "dbConnectionLimit": 60,
            },
        }).encode("utf-8")
        content_type = "application/json"
    else:
        body = b"<!doctype html><html></html>"
        content_type = "text/html"
    return {
        "path": path,
        "status": status,
        "durationMs": duration,
        "body": body,
        "contentType": content_type,
    }


class ProductionMonitorTests(unittest.TestCase):
    def _run(self, responses):
        output = io.StringIO()
        environment = {
            "COURSEPLATFORM_MONITOR_BASE_URL": "https://example.test",
            "COURSEPLATFORM_MONITOR_JOB_SECRET": "test-secret",
            "COURSEPLATFORM_MONITOR_LATENCY_MS": "2500",
            "COURSEPLATFORM_MONITOR_DB_PERCENT": "80",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(monitor_production, "_request", side_effect=responses),
            redirect_stdout(output),
        ):
            result = monitor_production.main()
        return result, json.loads(output.getvalue())

    def test_healthy_production_passes_without_exposing_secret(self):
        responses = [
            _response("/health/live"),
            _response("/health/ready"),
            _response("/"),
            _response("/health/metrics"),
        ]
        result, report = self._run(responses)
        self.assertEqual(0, result)
        self.assertEqual("ok", report["status"])
        self.assertNotIn("test-secret", json.dumps(report))

    def test_server_error_latency_and_saturation_fail_monitor(self):
        responses = [
            _response("/health/live", status=503, duration=3000),
            _response("/health/ready"),
            _response("/"),
            _response("/health/metrics", metrics_percent=85),
        ]
        result, report = self._run(responses)
        self.assertEqual(1, result)
        self.assertEqual("failed", report["status"])
        self.assertTrue(any("HTTP 503" in item for item in report["failures"]))
        self.assertTrue(any("85%" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
