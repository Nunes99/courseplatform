from contextlib import contextmanager
import time
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


APPLICATION_SCHEMA_COMPONENT = "application"
EXPECTED_SCHEMA_VERSION = 20260925120000


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


def schema_status_with_conn(conn) -> dict[str, Any]:
    relation_row = conn.execute(
        """
        select
          to_regclass('courseplatform.students') is not null as students_ready,
          to_regclass('courseplatform.admins') is not null as admins_ready,
          to_regclass('courseplatform.schema_versions') is not null as version_table_ready
        """
    ).fetchone()
    relation_row = relation_row or {}
    core_ready = bool(relation_row.get("students_ready") and relation_row.get("admins_ready"))
    version_table_ready = bool(relation_row.get("version_table_ready"))
    if not core_ready or not version_table_ready:
        return {
            "compatible": False,
            "installedVersion": None,
            "expectedVersion": EXPECTED_SCHEMA_VERSION,
            "reason": "SCHEMA_MISSING" if not core_ready else "VERSION_TABLE_MISSING",
        }

    version_row = conn.execute(
        """
        select version
        from courseplatform.schema_versions
        where component = %s
        """,
        (APPLICATION_SCHEMA_COMPONENT,),
    ).fetchone()
    installed_version = int(version_row["version"]) if version_row and version_row.get("version") is not None else None
    return {
        "compatible": installed_version == EXPECTED_SCHEMA_VERSION,
        "installedVersion": installed_version,
        "expectedVersion": EXPECTED_SCHEMA_VERSION,
        "reason": "READY" if installed_version == EXPECTED_SCHEMA_VERSION else "VERSION_MISMATCH",
    }


def schema_status() -> dict[str, Any]:
    with connection() as conn:
        return schema_status_with_conn(conn)


def schema_exists() -> bool:
    return bool(schema_status()["compatible"])
