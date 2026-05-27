# C:\Workspaces\port_strategy_execution\execution_db.py

import psycopg2
import psycopg2.extras

from db_config import get_db_config


def get_conn():
    return psycopg2.connect(**get_db_config())


def fetch_one(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        return cur.fetchone()


def fetch_all(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        return cur.fetchall()


def execute_one(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        try:
            return cur.fetchone()
        except psycopg2.ProgrammingError:
            return None
