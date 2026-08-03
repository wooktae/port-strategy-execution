from __future__ import annotations

import importlib
import os
from pathlib import Path


EXPECTED_PASSWORD = "container-smoke-placeholder"

REQUIRED_MODULES = [
    "execution_buy_sizing",
    "execution_daily_signal_builder",
    "execution_sync_buy_fill",
    "execution_validate_order_chain",
]

REQUIRED_FILES = [
    Path("/app/daily_auto_buy_execute_run.py"),
    Path("/app/execution_buy_sizing.py"),
    Path("/app/execution_daily_signal_builder.py"),
    Path("/app/execution_sync_buy_fill.py"),
    Path("/app/execution_validate_order_chain.py"),
    Path("/app/requirements.txt"),
]

FORBIDDEN_PATHS = [
    Path("/app/tests"),
    Path("/app/docs"),
    Path("/app/.git"),
    Path("/app/.github"),
    Path("/app/.devops"),
]


def verify_environment() -> None:
    password = os.environ.get("INTEREST_DB_PASSWORD")

    if password != EXPECTED_PASSWORD:
        raise RuntimeError(
            "Unexpected INTEREST_DB_PASSWORD smoke value"
        )

    print("SMOKE_ENVIRONMENT=SUCCESS")
    print("SMOKE_DB_PASSWORD=PLACEHOLDER_ONLY")


def verify_runtime_files() -> None:
    missing = [
        str(path)
        for path in REQUIRED_FILES
        if not path.is_file()
    ]

    if missing:
        raise RuntimeError(
            "Missing runtime files: " + ", ".join(missing)
        )

    forbidden = [
        str(path)
        for path in FORBIDDEN_PATHS
        if path.exists()
    ]

    if forbidden:
        raise RuntimeError(
            "Forbidden runtime paths: " + ", ".join(forbidden)
        )

    print("RUNTIME_REQUIRED_FILES=PRESENT")
    print("RUNTIME_FORBIDDEN_PATHS=ABSENT")


def verify_imports() -> None:
    for module_name in REQUIRED_MODULES:
        importlib.import_module(module_name)
        print(f"IMPORT={module_name} SUCCESS")

    print("RUNTIME_IMPORT_CONTRACT=SUCCESS")


def main() -> None:
    verify_environment()
    verify_runtime_files()
    verify_imports()

    print("DB_CONNECTION_ATTEMPTED=NO")
    print("ORDER_ENTRYPOINT_EXECUTED=NO")
    print("EXECUTION_CONTAINER_SMOKE=SUCCESS")


if __name__ == "__main__":
    main()
