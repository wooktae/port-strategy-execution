# C:\Workspaces\port_strategy_execution\execution_config.py

import os
from decimal import Decimal


DB_CONFIG = {
    "host": os.getenv("PORT_DB_HOST", "localhost"),
    "port": int(os.getenv("PORT_DB_PORT", "5433")),
    "dbname": os.getenv("PORT_DB_NAME", "interest_crawler"),
    "user": os.getenv("PORT_DB_USER", "postgres"),
    "password": os.getenv("PORT_DB_PASSWORD", ""),
}


ACCOUNT_NO = os.getenv("PORT_ACCOUNT_NO", "50187518")
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