"""Preflight, apply and verify the M4 platform onboarding foundation."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_VERSION = 20261012120000
PREVIOUS_VERSION = 20261011120000
MIGRATION_NAME = "add_platform_onboarding_foundation"
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20261012120000_add_platform_onboarding_foundation.sql"
)
REQUIRED_TABLES = {
    "platform_operators",
    "platform_sessions",
    "organization_onboarding_requests",
    "platform_audit_log",
}

OWNER_CANDIDATES_SQL = """
  select distinct students.student_id
  from courseplatform.organization_memberships membership
  join courseplatform.admins admins
    on admins.admin_id = membership.admin_id
  join courseplatform.organizations organizations
    on organizations.organization_id = membership.organization_id
  join courseplatform.students students
    on students.student_id = admins.student_id
    or (
      admins.student_id is null
      and lower(students.email) = lower(admins.email)
    )
  where membership.membership_role = 'OWNER'
    and membership.status = 'ACTIVE'
    and admins.status = 'ACTIVE'
    and students.status = 'ACTIVE'
    and organizations.status = 'ACTIVE'
"""


def connection_url() -> str:
    load_dotenv(ROOT / ".env")
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL não configurada.")
    return value


def migration_sql() -> tuple[str, str]:
    sql = MIGRATION.read_text(encoding="utf-8")
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest().upper()
    return sql, digest


def application_version(conn: psycopg.Connection) -> int:
    row = conn.execute(
        """
        select coalesce((
          select version from courseplatform.schema_versions
          where component = 'application'
        ), 0) as version
        """
    ).fetchone()
    return int(row["version"])


def sole_owner_candidate_count(conn: psycopg.Connection) -> int:
    row = conn.execute(
        f"select count(*) as total from ({OWNER_CANDIDATES_SQL}) candidates"
    ).fetchone()
    return int(row["total"] or 0)


def preflight(conn: psycopg.Connection) -> dict:
    version = application_version(conn)
    row = conn.execute(
        """
        select current_user as role,
               has_schema_privilege(current_user, 'courseplatform', 'CREATE') as can_create,
               exists(
                 select 1 from supabase_migrations.schema_migrations
                 where version = %s
               ) as recorded,
               (select count(*) from courseplatform.organizations) as organizations
        """,
        (str(MIGRATION_VERSION),),
    ).fetchone()
    candidates = sole_owner_candidate_count(conn)
    diagnostics = conn.execute(
        """
        select
          (select count(*) from courseplatform.admins
           where status = 'ACTIVE' and upper(role) = 'OWNER') as active_admin_owners,
          (select count(*) from courseplatform.organization_memberships
           where status = 'ACTIVE' and membership_role = 'OWNER') as active_membership_owners,
          (select count(*) from courseplatform.admins admins
           join courseplatform.students students on students.student_id = admins.student_id
           where admins.status = 'ACTIVE' and upper(admins.role) = 'OWNER'
             and students.status = 'ACTIVE') as linked_owner_identities,
          (select count(*) from courseplatform.admins admins
           join courseplatform.students students
             on lower(students.email) = lower(admins.email)
           where admins.status = 'ACTIVE' and upper(admins.role) = 'OWNER'
             and students.status = 'ACTIVE') as email_matched_owner_identities
        """
    ).fetchone()
    result = {
        "role": row["role"],
        "version": version,
        "can_migrate": bool(row["can_create"]),
        "recorded": bool(row["recorded"]),
        "organizations": int(row["organizations"]),
        "sole_owner_candidates": candidates,
    }
    print(f"role={result['role']}")
    print(f"schema_version={version}")
    print(f"can_migrate={str(result['can_migrate']).lower()}")
    print(f"migration_recorded={str(result['recorded']).lower()}")
    print(f"organizations={result['organizations']}")
    print(f"eligible_owner_identities={candidates}")
    print(f"active_admin_owners={int(diagnostics['active_admin_owners'] or 0)}")
    print(f"active_membership_owners={int(diagnostics['active_membership_owners'] or 0)}")
    print(f"linked_owner_identities={int(diagnostics['linked_owner_identities'] or 0)}")
    print(f"email_matched_owner_identities={int(diagnostics['email_matched_owner_identities'] or 0)}")
    if version not in {PREVIOUS_VERSION, MIGRATION_VERSION}:
        raise RuntimeError(f"Versão remota inesperada: {version}.")
    return result


def bootstrap_sole_owner(conn: psycopg.Connection) -> bool:
    existing = conn.execute(
        "select count(*) as total from courseplatform.platform_operators"
    ).fetchone()
    if int(existing["total"] or 0) > 0:
        print("platform_operator_bootstrap=already_configured")
        return False
    if sole_owner_candidate_count(conn) != 1:
        raise RuntimeError(
            "A atribuição automática exige exatamente uma identidade OWNER ativa e ligada."
        )
    inserted = conn.execute(
        """
        with candidate as (
          {OWNER_CANDIDATES_SQL}
        ), created as (
          insert into courseplatform.platform_operators
            (operator_id, student_id, operator_role, status)
          select
            'POP-' || upper(substr(md5('PLATFORM:' || student_id), 1, 12)),
            student_id,
            'GLOBAL_OWNER',
            'ACTIVE'
          from candidate
          returning operator_id
        )
        select operator_id from created
        """.format(OWNER_CANDIDATES_SQL=OWNER_CANDIDATES_SQL)
    ).fetchone()
    if not inserted:
        raise RuntimeError("O primeiro operador global não foi criado.")
    conn.execute(
        """
        insert into courseplatform.platform_audit_log
          (event_id, operator_id, action, entity_type, entity_id, details_json)
        values (
          'PEV-' || upper(substr(md5('BOOTSTRAP:' || %s), 1, 12)),
          %s,
          'PLATFORM_OPERATOR_BOOTSTRAPPED',
          'PLATFORM_OPERATOR',
          %s,
          '{"source":"SOLE_ACTIVE_INSTITUTIONAL_OWNER"}'::jsonb
        )
        on conflict (event_id) do nothing
        """,
        (inserted["operator_id"], inserted["operator_id"], inserted["operator_id"]),
    )
    print("platform_operator_bootstrap=created")
    return True


def postflight(conn: psycopg.Connection, expected_organizations: int | None = None) -> None:
    version = application_version(conn)
    rows = conn.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = 'courseplatform'
          and table_name = any(%s)
        """,
        (list(REQUIRED_TABLES),),
    ).fetchall()
    tables = {row["table_name"] for row in rows}
    operator_row = conn.execute(
        """
        select count(*) as total,
               count(*) filter (where status = 'ACTIVE') as active,
               count(*) filter (where operator_role = 'GLOBAL_OWNER') as global_owners
        from courseplatform.platform_operators
        """
    ).fetchone()
    organization_count = int(
        conn.execute("select count(*) as total from courseplatform.organizations").fetchone()["total"]
    )
    provisioned_requests = int(
        conn.execute(
            """
            select count(*) as total
            from courseplatform.organization_onboarding_requests
            where provisioned_organization_id is not null
            """
        ).fetchone()["total"]
    )
    missing = sorted(REQUIRED_TABLES - tables)
    print(f"postflight_schema_version={version}")
    print(f"postflight_required_tables={len(tables)}/{len(REQUIRED_TABLES)}")
    print(f"postflight_active_operators={int(operator_row['active'] or 0)}")
    print(f"postflight_global_owners={int(operator_row['global_owners'] or 0)}")
    print(f"postflight_organizations={organization_count}")
    print(f"postflight_provisioned_requests={provisioned_requests}")
    if (
        version != MIGRATION_VERSION
        or missing
        or provisioned_requests
        or (expected_organizations is not None and organization_count != expected_organizations)
    ):
        raise RuntimeError(
            "O pós-flight da M4 falhou: "
            f"missing={missing}, organizations={organization_count}."
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--bootstrap-sole-owner", action="store_true")
    parser.add_argument("--postflight", action="store_true")
    args = parser.parse_args()
    if args.bootstrap_sole_owner and not args.apply:
        parser.error("--bootstrap-sole-owner exige --apply.")

    sql, digest = migration_sql()
    print(f"migration_sha256={digest}")
    with psycopg.connect(connection_url(), row_factory=dict_row) as conn:
        state = preflight(conn)
        if args.postflight:
            postflight(conn)
            return 0
        if not args.apply:
            print("mode=preflight_only")
            return 0
        if state["version"] != MIGRATION_VERSION:
            if not state["can_migrate"]:
                raise RuntimeError("A role configurada não possui privilégios de migração.")
            conn.execute(sql)
        if not state["recorded"]:
            conn.execute(
                """
                insert into supabase_migrations.schema_migrations
                  (version, statements, name)
                values (%s, %s, %s)
                """,
                (str(MIGRATION_VERSION), [sql], MIGRATION_NAME),
            )
        if args.bootstrap_sole_owner:
            bootstrap_sole_owner(conn)
        postflight(conn, expected_organizations=state["organizations"])
        conn.commit()
    print("m4_platform_onboarding=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
