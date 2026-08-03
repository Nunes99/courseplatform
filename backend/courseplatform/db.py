from contextlib import contextmanager
from pathlib import Path
import time
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row

from .config import get_settings

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "schema.sql"


def _split_schema_sql(schema_sql: str) -> tuple[str, str]:
    markers = [
        "grant usage on schema courseplatform",
        "-- Public management views.",
    ]
    indexes = [schema_sql.find(marker) for marker in markers if schema_sql.find(marker) >= 0]
    if not indexes:
        return schema_sql, ""
    split_at = min(indexes)
    return schema_sql[:split_at], schema_sql[split_at:]


def _sql_statements(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def _connect():
    settings = get_settings()
    settings.require_database()
    last_error = None
    attempts = max(1, settings.db_connect_retries)
    for attempt in range(attempts):
        try:
            return psycopg.connect(
                settings.database_url,
                connect_timeout=settings.db_connect_timeout,
                row_factory=dict_row,
                # Supabase/Supavisor transaction pooling can move consecutive
                # transactions to different server sessions. Named prepared
                # statements are session-scoped and may therefore collide
                # (for example: "_pg3_0 already exists"). Keep queries on the
                # extended protocol without Psycopg's automatic preparation.
                prepare_threshold=None,
            )
        except psycopg.OperationalError as error:
            last_error = error
            if not _is_retriable_operational_error(error) or attempt >= attempts - 1:
                raise
            time.sleep(0.35 * (attempt + 1))
    raise last_error


def _read_with_retry(operation):
    settings = get_settings()
    attempts = max(1, settings.db_connect_retries)
    for attempt in range(attempts):
        try:
            return operation()
        except psycopg.OperationalError as error:
            if not _is_retriable_operational_error(error) or attempt >= attempts - 1:
                raise
            time.sleep(0.35 * (attempt + 1))


def _is_retriable_operational_error(error: psycopg.OperationalError) -> bool:
    text = str(error).lower()
    if "ecircuitbreaker" in text:
        return False
    if "authentication" in text or "password" in text:
        return False
    return True


@contextmanager
def connection():
    with _connect() as conn:
        yield conn


def fetch_one(query: str, params: Iterable[Any] | dict[str, Any] = ()):
    def operation():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()

    return _read_with_retry(operation)


def fetch_all(query: str, params: Iterable[Any] | dict[str, Any] = ()):
    def operation():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()

    return _read_with_retry(operation)


def execute(query: str, params: Iterable[Any] | dict[str, Any] = ()):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()


def schema_exists() -> bool:
    row = fetch_one(
        """
        select
          to_regclass('courseplatform.students') is not null
          and to_regclass('courseplatform.admins') is not null
          and exists (
            select 1 from information_schema.columns
            where table_schema = 'courseplatform' and table_name = 'students' and column_name = 'password_hash'
          )
          and exists (
            select 1 from information_schema.columns
            where table_schema = 'courseplatform' and table_name = 'admins' and column_name = 'password_hash'
          ) as ok
        """
    )
    return bool(row and row["ok"])


def ensure_schema() -> bool:
    if schema_exists():
        return False
    schema_sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    critical_sql, optional_sql = _split_schema_sql(schema_sql)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(critical_sql)
        conn.commit()
    if optional_sql:
        with connection() as conn:
            for statement in _sql_statements(optional_sql):
                try:
                    with conn.cursor() as cur:
                        cur.execute(statement)
                    conn.commit()
                except psycopg.Error:
                    conn.rollback()
    return True
