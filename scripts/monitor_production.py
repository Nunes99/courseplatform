"""External, non-destructive production monitor for CoursePlatform."""

import json
import os
import sys
import time
import urllib.error
import urllib.request


def _integer_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _request(base_url: str, path: str, secret: str = "") -> dict:
    request_id = f"external-monitor-{path.strip('/').replace('/', '-') or 'root'}"
    headers = {
        "Accept": "application/json" if path != "/" else "text/html",
        "User-Agent": "CoursePlatform-External-Monitor/1.0",
        "X-Request-ID": request_id,
    }
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(512_000)
            status = response.status
            content_type = response.headers.get("content-type", "").lower()
    except urllib.error.HTTPError as error:
        body = error.read(512_000)
        status = error.code
        content_type = error.headers.get("content-type", "").lower()
    duration_ms = round((time.monotonic() - started) * 1000)
    return {
        "path": path,
        "status": status,
        "durationMs": duration_ms,
        "body": body,
        "contentType": content_type,
    }


def main() -> int:
    base_url = os.getenv("COURSEPLATFORM_MONITOR_BASE_URL", "").strip().rstrip("/")
    secret = os.getenv("COURSEPLATFORM_MONITOR_JOB_SECRET", "").strip()
    latency_limit = _integer_env("COURSEPLATFORM_MONITOR_LATENCY_MS", 2500, 100, 30000)
    connection_limit = _integer_env(
        "COURSEPLATFORM_MONITOR_DB_PERCENT", 80, 1, 100
    )
    if not base_url.startswith("https://"):
        print("COURSEPLATFORM_MONITOR_BASE_URL must be an HTTPS URL.", file=sys.stderr)
        return 2
    if not secret:
        print("COURSEPLATFORM_MONITOR_JOB_SECRET is required.", file=sys.stderr)
        return 2

    results = []
    failures = []
    for path, expected_content in (
        ("/health/live", {"status": "ok"}),
        ("/health/ready", {"status": "ready"}),
    ):
        result = _request(base_url, path)
        try:
            parsed = json.loads(result.pop("body").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        result["bodyValid"] = parsed == expected_content
        results.append(result)
        if result["status"] != 200 or not result["bodyValid"]:
            failures.append(f"{path} returned an invalid response")
        if result["durationMs"] > latency_limit:
            failures.append(f"{path} exceeded {latency_limit} ms")

    root = _request(base_url, "/")
    root_body = root.pop("body")
    root["bodyValid"] = "text/html" in root["contentType"] and b"<html" in root_body.lower()
    results.append(root)
    if root["status"] != 200 or not root["bodyValid"]:
        failures.append("/ returned an invalid response")
    if root["durationMs"] > latency_limit:
        failures.append(f"/ exceeded {latency_limit} ms")

    protected = _request(base_url, "/health/metrics", secret)
    try:
        metrics_payload = json.loads(protected.pop("body").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        metrics_payload = {}
    metrics = metrics_payload.get("metrics") if isinstance(metrics_payload, dict) else None
    protected["bodyValid"] = bool(
        isinstance(metrics, dict)
        and isinstance(metrics.get("dbConnectionUtilizationPercent"), int)
        and isinstance(metrics.get("dbConnectionLimit"), int)
    )
    protected["dbConnectionUtilizationPercent"] = (
        int(metrics.get("dbConnectionUtilizationPercent") or 0)
        if isinstance(metrics, dict) else None
    )
    results.append(protected)
    if protected["status"] != 200 or not protected["bodyValid"]:
        failures.append("/health/metrics returned an invalid protected response")
    elif protected["dbConnectionUtilizationPercent"] >= connection_limit:
        failures.append(
            "Postgres connection utilization reached "
            f"{protected['dbConnectionUtilizationPercent']}%"
        )
    if protected["durationMs"] > latency_limit:
        failures.append(f"/health/metrics exceeded {latency_limit} ms")

    for result in results:
        if int(result["status"]) >= 500:
            failures.append(f"{result['path']} returned HTTP {result['status']}")

    report = {
        "status": "failed" if failures else "ok",
        "thresholds": {
            "latencyMs": latency_limit,
            "dbConnectionPercent": connection_limit,
        },
        "checks": results,
        "failures": sorted(set(failures)),
    }
    print(json.dumps(report, ensure_ascii=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
