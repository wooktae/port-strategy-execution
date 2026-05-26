# C:\Workspaces\port_strategy_execution\execution_db.py

import psycopg2
import psycopg2.extras

from execution_config import DB_CONFIG


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


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