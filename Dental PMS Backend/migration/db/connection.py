"""
migration/db/connection.py
--------------------------
psycopg2 connection factory. Import `get_conn` to open a connection,
or use `managed_conn` as a context manager.
"""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from migration.config import cfg


def get_conn():
    """
    Open and return a psycopg2 connection using settings from config.py / .env.
    Caller is responsible for commit() and close().
    """
    conn = psycopg2.connect(cfg.dsn)
    conn.autocommit = False
    return conn


@contextmanager
def managed_conn():
    """
    Context manager: opens a connection, commits on success, rolls back on error.

    Usage:
        with managed_conn() as conn:
            cur = conn.cursor()
            cur.execute(...)
    """
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
