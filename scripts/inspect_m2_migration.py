"""Read-only preflight/postflight for the M2 communication migration."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.courseplatform.db import connection


VERSION = "20261004180000"
TABLES = (
    "notifications",
    "push_subscriptions",
    "telegram_link_tokens",
    "chat_rooms",
    "chat_presence",
)


def main() -> int:
    with connection() as conn:
        summary = conn.execute(
            """
            select current_user as role,
                   has_schema_privilege(current_user, 'courseplatform', 'CREATE') as can_migrate,
                   exists (
                     select 1 from courseplatform.organizations
                     where organization_id = 'ORG-LMTWEBNAIRS' and status = 'ACTIVE'
                   ) as legacy_organization_ready,
                   exists (
                     select 1 from supabase_migrations.schema_migrations where version = %s
                   ) as migration_recorded,
                   (select max(version) from supabase_migrations.schema_migrations) as latest_migration,
                   (select version from courseplatform.schema_versions where component = 'application') as application_version
            """,
            (VERSION,),
        ).fetchone() or {}
        columns = conn.execute(
            """
            select table_name, is_nullable, column_default
            from information_schema.columns
            where table_schema = 'courseplatform'
              and column_name = 'organization_id'
              and table_name = any(%s)
            order by table_name
            """,
            (list(TABLES),),
        ).fetchall()
        null_rows: dict[str, int] = {}
        for column in columns:
            table = column["table_name"]
            result = conn.execute(
                f"select count(*) as count from courseplatform.{table} where organization_id is null"
            ).fetchone() or {}
            null_rows[table] = int(result.get("count") or 0)
        conn.rollback()

    output = {
        **summary,
        "tenant_columns": {
            row["table_name"]: {
                "nullable": row["is_nullable"],
                "has_default": row.get("column_default") is not None,
                "null_rows": null_rows.get(row["table_name"], 0),
            }
            for row in columns
        },
    }
    print(json.dumps(output, ensure_ascii=True, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
