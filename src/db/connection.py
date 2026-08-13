"""Direct Postgres (psycopg) connection to Supabase.

A data pipeline (bulk upserts, views) is better served by a direct Postgres
connection than the REST client. Rows come back as dicts.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from config import get_settings


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Yield a committed-on-success, rolled-back-on-error connection."""
    settings = get_settings()
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(query: str, params: tuple[Any, ...] | None = None) -> list[dict]:
    """Run a read query and return all rows as dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
