"""Read-only Stage 3 access verification for an isolated Supabase staging DB."""

from __future__ import annotations

import os
import sys
from urllib.parse import unquote, urlsplit

import psycopg


COMPATIBILITY_VIEWS = {
    "students", "admins", "sessions", "courses", "lessons",
    "lesson_content", "questions", "question_options", "groups",
    "enrollments", "group_members", "chat_rooms", "chat_messages",
    "chat_reads", "chat_message_reports", "lesson_progress", "attempts",
    "answers", "files", "reviews", "notifications",
    "notification_deliveries", "notification_channel_settings",
    "notification_templates", "push_subscriptions", "certificates",
    "audit_log", "settings", "lists", "student_import",
    "student_import_results", "new_credentials", "media_content",
    "schema_guide",
}

SENSITIVE_VIEWS = {
    "students", "admins", "sessions", "questions", "question_options",
    "answers", "audit_log", "new_credentials",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def staging_database_url() -> str:
    url = os.getenv("STAGING_DATABASE_URL", "").strip()
    staging_ref = os.getenv("STAGING_SUPABASE_PROJECT_REF", "").strip()
    production_ref = os.getenv("PRODUCTION_SUPABASE_PROJECT_REF", "").strip()
    confirmed = os.getenv("ALLOW_STAGE3_STAGING_VALIDATION", "").strip() == "1"
    if not url or not staging_ref or not confirmed:
        fail(
            "Defina STAGING_DATABASE_URL, STAGING_SUPABASE_PROJECT_REF e "
            "ALLOW_STAGE3_STAGING_VALIDATION=1 para uma base isolada."
        )
    if production_ref and staging_ref == production_ref:
        fail("A referência de staging coincide com a referência de produção.")
    parsed = urlsplit(url)
    connection_identity = f"{unquote(parsed.username or '')}@{parsed.hostname or ''}"
    if staging_ref not in connection_identity:
        fail("STAGING_DATABASE_URL não corresponde à referência de staging declarada.")
    return url


def assert_metadata(conn: psycopg.Connection) -> tuple[int, int]:
    rows = conn.execute(
        """
        select relation.relname, coalesce(relation.reloptions, array[]::text[]),
               has_table_privilege('anon', relation.oid, 'SELECT'),
               has_table_privilege('anon', relation.oid, 'INSERT'),
               has_table_privilege('anon', relation.oid, 'UPDATE'),
               has_table_privilege('anon', relation.oid, 'DELETE'),
               has_table_privilege('authenticated', relation.oid, 'SELECT'),
               has_table_privilege('authenticated', relation.oid, 'INSERT'),
               has_table_privilege('authenticated', relation.oid, 'UPDATE'),
               has_table_privilege('authenticated', relation.oid, 'DELETE'),
               has_table_privilege('service_role', relation.oid, 'SELECT'),
               has_table_privilege('service_role', relation.oid, 'INSERT'),
               has_table_privilege('service_role', relation.oid, 'UPDATE'),
               has_table_privilege('service_role', relation.oid, 'DELETE')
        from pg_class relation
        join pg_namespace namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public'
          and relation.relkind = 'v'
          and relation.relname = any(%s)
        order by relation.relname
        """,
        (list(COMPATIBILITY_VIEWS),),
    ).fetchall()
    present = {row[0] for row in rows}
    missing_sensitive = SENSITIVE_VIEWS - present
    if missing_sensitive:
        fail(f"Views sensíveis esperadas ausentes: {', '.join(sorted(missing_sensitive))}")
    for row in rows:
        name, options, *privileges = row
        if "security_invoker=true" not in options:
            fail(f"public.{name} não usa security_invoker.")
        if any(privileges[:8]):
            fail(f"Uma role cliente ainda tem privilégios em public.{name}.")
        if not privileges[8] or any(privileges[9:]):
            fail(f"service_role não está limitada a SELECT em public.{name}.")

    table_rows = conn.execute(
        """
        select relation.relname, relation.relrowsecurity,
               has_table_privilege('anon', relation.oid, 'SELECT,INSERT,UPDATE,DELETE'),
               has_table_privilege('authenticated', relation.oid, 'SELECT,INSERT,UPDATE,DELETE')
        from pg_class relation
        join pg_namespace namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'courseplatform'
          and relation.relkind in ('r', 'p')
        order by relation.relname
        """
    ).fetchall()
    for name, rls_enabled, anon_access, authenticated_access in table_rows:
        if not rls_enabled:
            fail(f"RLS não está ativa em courseplatform.{name}.")
        if anon_access or authenticated_access:
            fail(f"Uma role cliente tem privilégios diretos em courseplatform.{name}.")
    return len(rows), len(table_rows)


def assert_function_access(conn: psycopg.Connection) -> None:
    topic = conn.execute(
        "select to_regprocedure('courseplatform.chat_realtime_topic_allowed(text,jsonb)')"
    ).fetchone()[0]
    if topic:
        checks = conn.execute(
            """
            select
              has_schema_privilege('authenticated', 'courseplatform', 'USAGE'),
              has_function_privilege('anon', %s, 'EXECUTE'),
              has_function_privilege('authenticated', %s, 'EXECUTE'),
              has_function_privilege('service_role', %s, 'EXECUTE')
            """,
            (topic, topic, topic),
        ).fetchone()
        if checks != (True, False, True, False):
            fail("A exceção Realtime não está limitada à role authenticated.")

    for signature in (
        "courseplatform.broadcast_chat_message_change()",
        "public.rls_auto_enable()",
    ):
        function_oid = conn.execute("select to_regprocedure(%s)", (signature,)).fetchone()[0]
        if not function_oid:
            continue
        exposed = conn.execute(
            """
            select has_function_privilege('anon', %s, 'EXECUTE')
                or has_function_privilege('authenticated', %s, 'EXECUTE')
                or has_function_privilege('service_role', %s, 'EXECUTE')
            """,
            (function_oid, function_oid, function_oid),
        ).fetchone()[0]
        if exposed:
            fail(f"A função operacional {signature} ainda é executável por uma role de API.")


def assert_storage(conn: psycopg.Connection) -> None:
    bucket = os.getenv("SUPABASE_CERTIFICATE_BUCKET", "courseplatform-certificate-assets").strip()
    bucket_row = conn.execute(
        "select public from storage.buckets where id = %s",
        (bucket,),
    ).fetchone()
    if bucket_row and bucket_row[0]:
        fail("O bucket de certificados está público.")
    client_policy_count = conn.execute(
        """
        select count(*)
        from pg_policies
        where schemaname = 'storage'
          and roles && array['public'::name, 'anon'::name, 'authenticated'::name]
        """
    ).fetchone()[0]
    if client_policy_count:
        fail("Existem policies de Storage para roles cliente; reveja-as por bucket e proprietário.")


def assert_runtime_denials(conn: psycopg.Connection) -> int:
    checks = 0
    for role in ("anon", "authenticated"):
        conn.execute(f"set role {role}")
        try:
            for view in sorted(SENSITIVE_VIEWS):
                try:
                    conn.execute(f'select 1 from public."{view}" limit 0')
                except psycopg.errors.InsufficientPrivilege:
                    checks += 1
                else:
                    fail(f"{role} conseguiu consultar public.{view}.")
        finally:
            conn.execute("reset role")
    return checks


def main() -> int:
    try:
        with psycopg.connect(staging_database_url(), autocommit=True) as conn:
            view_count, table_count = assert_metadata(conn)
            assert_function_access(conn)
            assert_storage(conn)
            denial_count = assert_runtime_denials(conn)
    except RuntimeError as error:
        print(f"FALHOU: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f"FALHOU: erro Postgres ({error.__class__.__name__}).", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"FALHOU: erro inesperado ({error.__class__.__name__}).", file=sys.stderr)
        return 1
    print(
        "OK: validação somente leitura concluída em staging; "
        f"{view_count} views, {table_count} tabelas e {denial_count} recusas verificadas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
