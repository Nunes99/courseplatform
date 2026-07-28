from contextlib import contextmanager
import time
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


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
            if attempt >= attempts - 1:
                raise
            time.sleep(0.35 * (attempt + 1))
    raise last_error


def _read_with_retry(operation):
    settings = get_settings()
    attempts = max(1, settings.db_connect_retries)
    for attempt in range(attempts):
        try:
            return operation()
        except psycopg.OperationalError:
            if attempt >= attempts - 1:
                raise
            time.sleep(0.35 * (attempt + 1))


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
