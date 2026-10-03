"""Non-destructive post-deploy checks; never authenticates or mutates data."""

import json
import os
import sys
import urllib.error
import urllib.request


def fetch(base_url: str, path: str) -> tuple[int, bytes, dict[str, str]]:
    request_id = f"courseplatform-smoke-{path.strip('/').replace('/', '-') or 'root'}"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        headers={
            "User-Agent": "CoursePlatform-Smoke/1.0",
            "X-Request-ID": request_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(512_000), {
                key.lower(): value for key, value in response.headers.items()
            }
    except urllib.error.HTTPError as error:
        return error.code, error.read(512_000), {
            key.lower(): value for key, value in error.headers.items()
        }


def main() -> int:
    base_url = os.getenv("COURSEPLATFORM_SMOKE_BASE_URL", "").strip()
    if not base_url.startswith(("https://", "http://")):
        print("COURSEPLATFORM_SMOKE_BASE_URL must be an HTTP(S) URL.", file=sys.stderr)
        return 2

    checks = []
    for path, expected_status, expected_json in (
        ("/health/live", 200, {"status": "ok"}),
        ("/health/ready", 200, {"status": "ready"}),
    ):
        status, body, headers = fetch(base_url, path)
        parsed = json.loads(body.decode("utf-8"))
        passed = (
            status == expected_status
            and parsed == expected_json
            and headers.get("x-request-id") == f"courseplatform-smoke-{path.strip('/').replace('/', '-')}"
        )
        checks.append({"path": path, "status": status, "passed": passed})

    status, body, headers = fetch(base_url, "/")
    content_type = headers.get("content-type", "").lower()
    checks.append({
        "path": "/",
        "status": status,
        "passed": status == 200 and "text/html" in content_type and b"<html" in body.lower(),
    })

    print(json.dumps({"checks": checks}, ensure_ascii=True))
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
