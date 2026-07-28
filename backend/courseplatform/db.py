from contextlib import contextmanager
from pathlib import Path
import time
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row

from .config import get_settings

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "schema.sql"


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
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    return True
