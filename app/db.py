"""Database connection pool and query helpers."""

import os
import time
import logging
from pathlib import Path

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from flask import g

logger = logging.getLogger(__name__)

_pool: pool.ThreadedConnectionPool | None = None


def _dsn() -> dict:
    return dict(
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.ThreadedConnectionPool(minconn=1, maxconn=10, **_dsn())
    return _pool


def get_db() -> psycopg2.extensions.connection:
    """Return the per-request connection (stored in Flask g)."""
    if "db_conn" not in g:
        g.db_conn = get_pool().getconn()
    return g.db_conn


def _run_migrations() -> None:
    sql_path = Path(__file__).parent.parent / "migrations" / "001_init.sql"
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text())
        conn.commit()
    finally:
        get_pool().putconn(conn)


def init_db(app) -> None:
    """Initialise pool and run migrations.  Retries until DB is ready."""
    for attempt in range(10):
        try:
            _run_migrations()
            logger.info("Database migrations applied successfully.")
            break
        except psycopg2.OperationalError as exc:
            if attempt == 9:
                raise
            logger.warning("DB not ready (attempt %d/10): %s — retrying in 2s", attempt + 1, exc)
            time.sleep(2)

    @app.teardown_appcontext
    def _release(exc):
        conn = g.pop("db_conn", None)
        if conn is not None:
            get_pool().putconn(conn)


def query(sql: str, params=None, fetch: str = "all"):
    """Execute *sql* and return rows as list-of-dicts (or single dict, or None)."""
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        if fetch == "all":
            result = [dict(r) for r in cur.fetchall()]
        elif fetch == "one":
            row = cur.fetchone()
            result = dict(row) if row else None
        else:
            result = None
    conn.commit()
    return result


def execute(sql: str, params=None) -> None:
    """Execute *sql* without returning rows (INSERT / UPDATE / DELETE)."""
    query(sql, params, fetch=None)
