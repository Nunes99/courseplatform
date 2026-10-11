"""Preflight, apply and verify the M3 operational isolation migration."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_VERSION = 20261005020000
PREVIOUS_VERSION = 20261004213604
DEFAULT_ORGANIZATION_ID = "ORG-LMTWEBNAIRS"
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20261005020000_isolate_operational_jobs_by_organization.sql"
)


def connection_url() -> str:
    load_dotenv(ROOT / ".env")
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL nao configurada.")
    return value


def _schema_version(conn: psycopg.Connection) -> int:
    row = conn.execute(
        """
        select coalesce((
          select version
          from courseplatform.schema_versions
          where component = 'application'
        ), 0)
        """
    ).fetchone()
    return int(row[0])


def preflight(conn: psycopg.Connection) -> tuple[int, bool]:
    row = conn.execute(
        """
        select current_user,
               (select pg_get_userbyid(relowner)
                from pg_class
                where oid = 'courseplatform.operational_jobs'::regclass),
               (select rolsuper from pg_roles where rolname = current_user)
        """
    ).fetchone()
    role, owner, superuser = row
    version = _schema_version(conn)
    can_migrate = bool(superuser) or bool(
        conn.execute(
            "select pg_has_role(current_user, %s, 'MEMBER')", (owner,)
        ).fetchone()[0]
    )
    default_organization_exists = bool(
        conn.execute(
            """
            select exists(
              select 1
              from courseplatform.organizations
              where organization_id = %s
            )
            """,
            (DEFAULT_ORGANIZATION_ID,),
        ).fetchone()[0]
    )
    columns = {
        row[0]
        for row in conn.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'courseplatform'
              and table_name = 'operational_jobs'
              and column_name in ('organization_id', 'dead_lettered_at')
            """
        ).fetchall()
    }
    total_jobs = int(
        conn.execute("select count(*) from courseplatform.operational_jobs").fetchone()[0]
    )
    null_organizations = total_jobs
    if "organization_id" in columns:
        null_organizations = int(
            conn.execute(
                """
                select count(*)
                from courseplatform.operational_jobs
                where organization_id is null
                """
            ).fetchone()[0]
        )

    print(f"role={role}")
    print(f"schema_version={version}")
    print(f"migration_owner={owner}")
    print(f"can_migrate={str(can_migrate).lower()}")
    print(
        "default_organization_exists="
        f"{str(default_organization_exists).lower()}"
    )
    print(f"operational_jobs={total_jobs}")
    print(f"jobs_requiring_organization_backfill={null_organizations}")
    if version not in {PREVIOUS_VERSION, MIGRATION_VERSION}:
        raise RuntimeError(f"Versao remota inesperada: {version}.")
    if null_organizations and not default_organization_exists:
        raise RuntimeError(
            "A instituicao padrao exigida pelo backfill nao existe."
        )
    return version, can_migrate


def postflight(conn: psycopg.Connection) -> None:
    version = _schema_version(conn)
    columns = int(
        conn.execute(
            """
            select count(*)
            from information_schema.columns
            where table_schema = 'courseplatform'
              and table_name = 'operational_jobs'
              and column_name in ('organization_id', 'dead_lettered_at')
            """
        ).fetchone()[0]
    )
    null_organizations = int(
        conn.execute(
            """
            select count(*)
            from courseplatform.operational_jobs
            where organization_id is null
            """
        ).fetchone()[0]
    )
    missing_dead_letter_timestamp = int(
        conn.execute(
            """
            select count(*)
            from courseplatform.operational_jobs
            where status = 'DEAD' and dead_lettered_at is null
            """
        ).fetchone()[0]
    )
    invalid_organization_references = int(
        conn.execute(
            """
            select count(*)
            from courseplatform.operational_jobs job
            left join courseplatform.organizations organization
              on organization.organization_id = job.organization_id
            where organization.organization_id is null
            """
        ).fetchone()[0]
    )
    duplicate_keys = int(
        conn.execute(
            """
            select count(*)
            from (
              select organization_id, idempotency_key
              from courseplatform.operational_jobs
              group by organization_id, idempotency_key
              having count(*) > 1
            ) duplicated
            """
        ).fetchone()[0]
    )
    constraint_row = conn.execute(
        """
        select convalidated
        from pg_constraint
        where conrelid = 'courseplatform.operational_jobs'::regclass
          and conname = 'operational_jobs_organization_id_fkey'
        """
    ).fetchone()
    unique_index = bool(
        conn.execute(
            """
            select exists(
              select 1
              from pg_indexes
              where schemaname = 'courseplatform'
                and tablename = 'operational_jobs'
                and indexname = 'uq_operational_jobs_organization_idempotency'
                and indexdef ilike 'create unique index%'
            )
            """
        ).fetchone()[0]
    )
    old_constraint = bool(
        conn.execute(
            """
            select exists(
              select 1
              from pg_constraint
              where conrelid = 'courseplatform.operational_jobs'::regclass
                and conname = 'operational_jobs_idempotency_key_key'
            )
            """
        ).fetchone()[0]
    )
    foreign_key_validated = bool(constraint_row and constraint_row[0])

    print(f"postflight_schema_version={version}")
    print(f"postflight_columns={columns}/2")
    print(f"postflight_null_organizations={null_organizations}")
    print(
        "postflight_missing_dead_letter_timestamp="
        f"{missing_dead_letter_timestamp}"
    )
    print(
        "postflight_invalid_organization_references="
        f"{invalid_organization_references}"
    )
    print(f"postflight_duplicate_keys={duplicate_keys}")
    print(f"postflight_foreign_key_validated={str(foreign_key_validated).lower()}")
    print(f"postflight_tenant_unique_index={str(unique_index).lower()}")
    print(f"postflight_old_unique_constraint={str(old_constraint).lower()}")

    failures = (
        version != MIGRATION_VERSION
        or columns != 2
        or null_organizations
        or missing_dead_letter_timestamp
        or invalid_organization_references
        or duplicate_keys
        or not foreign_key_validated
        or not unique_index
        or old_constraint
    )
    if failures:
        raise RuntimeError("O pos-flight da migracao M3 falhou.")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--postflight", action="store_true")
    args = parser.parse_args()

    with psycopg.connect(connection_url()) as conn:
        if args.postflight:
            postflight(conn)
            print("m3_operational_isolation=verified")
            return 0

        version, can_migrate = preflight(conn)
        if not args.apply:
            print("mode=preflight_only")
            return 0
        if version != MIGRATION_VERSION:
            if not can_migrate:
                raise RuntimeError(
                    "A role de DATABASE_URL nao possui privilegios de migracao."
                )
            conn.execute(MIGRATION.read_text(encoding="utf-8"))
            conn.commit()
        postflight(conn)

    print("m3_operational_isolation=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
