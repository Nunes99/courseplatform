"""Apply and verify the final M2 migration through a direct Postgres connection."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_VERSION = 20261004213604
PREVIOUS_VERSION = 20261004180000
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20261004213604_complete_m2_tenant_isolation.sql"
)
COMMUNICATION_TABLES = (
    "notifications",
    "push_subscriptions",
    "telegram_link_tokens",
    "chat_rooms",
    "chat_presence",
)


def connection_url() -> str:
    load_dotenv(ROOT / ".env")
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL não configurada.")
    return value


def preflight(conn: psycopg.Connection) -> tuple[int, bool]:
    row = conn.execute(
        """
        select current_user,
               coalesce((select version from courseplatform.schema_versions
                         where component = 'application'), 0),
               (select pg_get_userbyid(relowner)
                from pg_class where oid = 'courseplatform.audit_log'::regclass),
               (select rolsuper from pg_roles where rolname = current_user)
        """
    ).fetchone()
    role, version, owner, superuser = row
    can_migrate = bool(superuser) or bool(
        conn.execute("select pg_has_role(current_user, %s, 'MEMBER')", (owner,)).fetchone()[0]
    )
    print(f"role={role}")
    print(f"schema_version={version}")
    print(f"migration_owner={owner}")
    print(f"can_migrate={str(can_migrate).lower()}")
    if int(version) not in {PREVIOUS_VERSION, MIGRATION_VERSION}:
        raise RuntimeError(f"Versão remota inesperada: {version}.")
    return int(version), can_migrate


def postflight(conn: psycopg.Connection) -> None:
    version = conn.execute(
        "select version from courseplatform.schema_versions where component = 'application'"
    ).fetchone()[0]
    audit_invalid = conn.execute(
        """
        select count(*)
        from courseplatform.audit_log
        where scope not in ('PLATFORM', 'ORGANIZATION')
           or (scope = 'PLATFORM' and organization_id is not null)
           or (scope = 'ORGANIZATION' and organization_id is null)
        """
    ).fetchone()[0]
    public_columns = conn.execute(
        """
        select count(*)
        from information_schema.columns
        where table_schema = 'courseplatform'
          and (
            (table_name = 'organizations'
             and column_name in ('public_listing_status', 'public_profile_json'))
            or (table_name = 'courses' and column_name = 'catalog_visibility')
          )
        """
    ).fetchone()[0]
    defaults = conn.execute(
        """
        select table_name, column_default
        from information_schema.columns
        where table_schema = 'courseplatform'
          and table_name = any(%s)
          and column_name = 'organization_id'
        order by table_name
        """,
        (list(COMMUNICATION_TABLES),),
    ).fetchall()
    remaining_defaults = [table for table, default in defaults if default is not None]
    unvalidated = conn.execute(
        """
        select count(*)
        from pg_constraint
        where conrelid in (
          'courseplatform.audit_log'::regclass,
          'courseplatform.organizations'::regclass,
          'courseplatform.courses'::regclass
        )
          and conname in (
            'audit_log_organization_id_fkey',
            'audit_log_scope_check',
            'audit_log_scope_organization_check',
            'organizations_public_listing_status_check',
            'courses_catalog_visibility_check'
          )
          and not convalidated
        """
    ).fetchone()[0]
    print(f"postflight_schema_version={version}")
    print(f"postflight_audit_invalid={audit_invalid}")
    print(f"postflight_public_columns={public_columns}/3")
    print(f"postflight_communication_defaults={len(remaining_defaults)}")
    print(f"postflight_unvalidated_constraints={unvalidated}")
    if int(version) != MIGRATION_VERSION:
        raise RuntimeError("O marcador da migração não foi atualizado.")
    if audit_invalid or public_columns != 3 or remaining_defaults or unvalidated:
        raise RuntimeError("O pós-flight da migração falhou.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with psycopg.connect(connection_url()) as conn:
        version, can_migrate = preflight(conn)
        if args.apply and version != MIGRATION_VERSION:
            if not can_migrate:
                raise RuntimeError("A role de DATABASE_URL não possui privilégios de migração.")
            conn.execute(MIGRATION.read_text(encoding="utf-8"))
            conn.commit()
        elif not args.apply:
            print("mode=preflight_only")
            return 0
        postflight(conn)
    print("m2_completion_migration=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
