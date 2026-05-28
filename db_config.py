# C:\Workspaces\port_strategy_execution\db_config.py

"""
execution 모듈의 PostgreSQL 접속 설정을 환경변수에서 구성한다.
민감정보 값은 코드나 문서에 기록하지 않고 로컬 환경변수로 주입한다.
schema-per-domain 전환을 위한 search_path 옵션도 이곳에서 지정한다.
"""

import os


def get_db_config():
    """
    psycopg2.connect에 전달할 DB 설정 dict를 만든다.
    INTEREST_DB_PASSWORD는 필수 환경변수로 요구하며 실제 값은 출력하지 않는다.
    """
    password = os.getenv("INTEREST_DB_PASSWORD")
    if not password:
        raise RuntimeError("INTEREST_DB_PASSWORD environment variable is required")

    return {
        "host": os.getenv("INTEREST_DB_HOST", "localhost"),
        "port": int(os.getenv("INTEREST_DB_PORT", "5433")),
        "dbname": os.getenv("INTEREST_DB_NAME", "portfolio"),
        "user": os.getenv("INTEREST_DB_USER", "postgres"),
        "password": password,
        "options": "-c search_path=execution,decision,research,connector,preprocessor,interest,reference,legacy,public",
    }
