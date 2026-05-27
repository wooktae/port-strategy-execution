# C:\Workspaces\port_strategy_execution\db_config.py

import os


def get_db_config():
    password = os.getenv("INTEREST_DB_PASSWORD")
    if not password:
        raise RuntimeError("INTEREST_DB_PASSWORD environment variable is required")

    return {
        "host": os.getenv("INTEREST_DB_HOST", "localhost"),
        "port": int(os.getenv("INTEREST_DB_PORT", "5433")),
        "dbname": os.getenv("INTEREST_DB_NAME", "interest_crawler"),
        "user": os.getenv("INTEREST_DB_USER", "postgres"),
        "password": password,
    }
