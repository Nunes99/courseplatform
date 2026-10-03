"""Configure the production job scheduler without exposing its bearer secret."""

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.courseplatform.db import connection


DEFAULT_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20261003120000_schedule_operational_worker.sql"
)


def _upsert_vault_secret(conn, name: str, value: str, description: str) -> None:
    # Serialize scheduler configuration without requiring UPDATE on Vault's
    # internal secrets table. Mutations remain confined to Vault's functions.
    conn.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"courseplatform:vault:{name}",),
    )
    row = conn.execute(
        "select id from vault.secrets where name = %s",
        (name,),
    ).fetchone()
    if row:
        conn.execute(
            "select vault.update_secret(%s, %s, %s, %s)",
            (row["id"], value, name, description),
        )
        return
    conn.execute(
        "select vault.create_secret(%s, %s, %s)",
        (value, name, description),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-file", type=Path, required=True)
    parser.add_argument("--platform-url", required=True)
    parser.add_argument("--migration", type=Path, default=DEFAULT_MIGRATION)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.apply:
        parser.error("A configuração externa exige --apply.")
    parsed_url = urlsplit(args.platform_url.strip())
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        parser.error("--platform-url deve ser uma URL HTTPS absoluta.")

    secret = args.secret_file.read_text(encoding="ascii").strip()
    if len(secret.encode("utf-8")) < 32:
        parser.error("O segredo deve possuir pelo menos 32 bytes.")
    migration_sql = args.migration.read_text(encoding="utf-8")

    load_dotenv(ROOT / ".env")
    with connection() as conn:
        _upsert_vault_secret(
            conn,
            "courseplatform_platform_url",
            args.platform_url.rstrip("/"),
            "URL do deployment usada pelo worker operacional.",
        )
        _upsert_vault_secret(
            conn,
            "courseplatform_job_runner_secret",
            secret,
            "Bearer secret do executor operacional CoursePlatform.",
        )
        conn.execute(migration_sql)

        row = conn.execute(
            """
            select active, schedule
            from cron.job
            where jobname = 'courseplatform-operational-worker'
            """
        ).fetchone()

    result = {
        "vaultSecretsConfigured": True,
        "cronActive": bool(row and row["active"]),
        "schedule": row["schedule"] if row else None,
    }
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["cronActive"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
