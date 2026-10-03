"""Validate recovery evidence without accessing production systems."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "recovery-drills.json"
MIGRATION_PATTERN = re.compile(r"^(\d{12}|\d{14})_[a-z0-9_]+\.sql$")
REQUIRED_FILES = (
    "docs/stage13-reliable-operations.md",
    "docs/database-migrations.md",
    "scripts/smoke_post_deploy.py",
    "scripts/validate_private_downloads.py",
)


def evaluate_drill_schedule(last_drill: date, frequency_days: int, today: date) -> dict:
    due_date = last_drill + timedelta(days=frequency_days)
    return {
        "lastDrill": last_drill.isoformat(),
        "nextDrillDue": due_date.isoformat(),
        "overdue": today > due_date,
        "daysUntilDue": (due_date - today).days,
    }


def inspect_repository(today: date | None = None) -> dict:
    current_date = today or datetime.now(timezone.utc).date()
    checks: list[dict] = []

    for relative_path in REQUIRED_FILES:
        exists = (ROOT / relative_path).is_file()
        checks.append({"name": relative_path, "passed": exists})

    migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    migration_ids = []
    valid_migration_names = True
    for migration in migrations:
        match = MIGRATION_PATTERN.fullmatch(migration.name)
        if not match:
            valid_migration_names = False
            continue
        migration_ids.append(match.group(1))
    checks.append(
        {
            "name": "versioned migrations",
            "passed": bool(migrations)
            and valid_migration_names
            and len(migration_ids) == len(set(migration_ids)),
            "count": len(migrations),
        }
    )

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    policy = registry["policy"]
    drills = registry["drills"]
    frequency_days = int(policy["frequencyDays"])
    latest = max(drills, key=lambda item: item["date"])
    schedule = evaluate_drill_schedule(
        date.fromisoformat(latest["date"]), frequency_days, current_date
    )
    latest_valid = (
        latest.get("result") == "passed"
        and latest.get("productionDataUsed") is False
        and int(latest.get("databaseTables", 0)) > 0
        and int(latest.get("storageObjects", 0)) > 0
    )
    checks.append({"name": "latest recovery drill evidence", "passed": latest_valid})

    invalid = any(not check["passed"] for check in checks)
    status = "invalid" if invalid else "overdue" if schedule["overdue"] else "ready"
    return {
        "status": status,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "frequencyDays": frequency_days,
            "rpoHours": int(policy["rpoHours"]),
            "rtoHours": int(policy["rtoHours"]),
        },
        "schedule": schedule,
        "checks": checks,
        "requiresExternalDrill": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fail-if-overdue", action="store_true")
    args = parser.parse_args()
    report = inspect_repository()
    payload = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if args.report:
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if report["status"] == "invalid":
        return 1
    if args.fail_if_overdue and report["status"] == "overdue":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
