# C:\Workspaces\port_strategy_execution\execution_config.py

"""
execution 모듈의 환경변수 기반 설정을 모으는 파일.
DB, 계좌, broker, strategy, sizing 관련 key를 읽지만 민감정보 값은 문서화하지 않는다.
설정명과 기본 정책은 다른 실행 스크립트가 공유하므로 임의 변경하지 않는다.
"""

import os
from decimal import Decimal

from db_config import get_db_config


DB_CONFIG = get_db_config()


ACCOUNT_NO = os.getenv("PORT_ACCOUNT_NO")

if not ACCOUNT_NO:
    raise RuntimeError("PORT_ACCOUNT_NO is required")
BROKER_NAME = os.getenv("PORT_BROKER_NAME", "koreainvestment")
ENVIRONMENT = os.getenv("PORT_ENVIRONMENT", "paper")


STRATEGY_NAME = os.getenv("PORT_STRATEGY_NAME", "strategy_ai")
STRATEGY_VERSION = os.getenv("PORT_STRATEGY_VERSION", "RESEARCH_V3_EXIT_SOFTENED")


DEFAULT_MAX_ORDER_AMOUNT_RATIO = Decimal(
    os.getenv("PORT_MAX_ORDER_AMOUNT_RATIO", "0.50")
)

MIN_ORDER_AMOUNT = Decimal(
    os.getenv("PORT_MIN_ORDER_AMOUNT", "10000")
)
