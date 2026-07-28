from contextlib import contextmanager
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


@contextmanager
def connection():
    settings = get_settings()
    settings.require_database()
    with psycopg.connect(
        settings.database_url,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        yield conn


def fetch_one(query: str, params: Iterable[Any] | dict[str, Any] = ()):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetch_all(query: str, params: Iterable[Any] | dict[str, Any] = ()):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def execute(query: str, params: Iterable[Any] | dict[str, Any] = ()):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
