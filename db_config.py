"""
Builds the PostgreSQL connection settings for the execution module from environment variables.
Sensitive values are not recorded in code or documentation and are injected via local environment variables.
The search_path option for the schema-per-domain transition is also specified here.
"""

import os


def get_db_config():
    """
    Builds the DB settings dict to pass to psycopg2.connect.
    INTEREST_DB_PASSWORD is required as an environment variable, and its actual value is not printed.
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
