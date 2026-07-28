from contextlib import contextmanager
from typing import Any, Iterable

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        settings.require_database()
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=0,
            max_size=5,
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def connection():
    with pool().connection() as conn:
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
