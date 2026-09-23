# C:\Workspaces\port_strategy_execution\execution_config.py

"""
File that gathers the environment-variable-based settings for the execution module.
It reads DB, account, broker, strategy, and sizing keys, but does not document sensitive values.
The setting names and default policies are shared by other execution scripts, so do not change them arbitrarily.
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
