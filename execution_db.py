# C:\Workspaces\port_strategy_execution\execution_db.py

"""
execution 모듈의 psycopg2 DB helper.
공통 DB 설정과 RealDictCursor 기반 fetch/execute helper를 제공한다.
이 파일의 함수 호출 자체는 실제 DB 접속 또는 SQL 실행으로 이어진다.
"""

import psycopg2
import psycopg2.extras

from db_config import get_db_config


def get_conn():
    """공통 환경변수 설정으로 PostgreSQL connection을 생성한다."""
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
