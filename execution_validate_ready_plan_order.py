"""
Validate READY execution plan -> execution order consistency.

Read-only validation rules:
- Find the latest execution plan for the requested plan_date.
- If no plan exists, fail unless --allow-no-plan is explicitly used.
- If plan_status = READY and ready_order_count > 0:
  - at least one execution order must exist,
  - PAPER_STRATEGY order count must equal ready_order_count,
  - every order must reference the same execution_plan_id,
  - no order may have invalid quantity or missing action/ticker.
- If ready_order_count = 0, no order is required.

This script never inserts, updates, or deletes DB rows.
"""

import argparse
import json
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from psycopg.rows import dict_row as _psycopg3_dict_row
except ImportError:
    _psycopg3_dict_row = None

try:
    from psycopg2.extras import RealDictCursor as _psycopg2_real_dict_cursor
except ImportError:
    _psycopg2_real_dict_cursor = None

from execution_db import get_conn


EXECUTION_MODE = "PAPER_STRATEGY"


def _dict_cursor(conn):
    if _psycopg3_dict_row is not None:
        try:
            return conn.cursor(row_factory=_psycopg3_dict_row)
        except TypeError:
            pass

    if _psycopg2_real_dict_cursor is not None:
        try:
            return conn.cursor(cursor_factory=_psycopg2_real_dict_cursor)
        except TypeError:
            pass

    raise RuntimeError(
        "DICT_CURSOR_NOT_SUPPORTED:"
        f"connection_type={type(conn).__module__}.{type(conn).__name__}"
    )


def _quote_identifier(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum():
        raise RuntimeError(f"invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def _table_info(conn, table_name: str) -> Tuple[str, set]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, column_name
            FROM information_schema.columns
            WHERE table_name = %s
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY
                CASE
                    WHEN table_schema = current_schema() THEN 0
                    WHEN table_schema = 'public' THEN 1
                    ELSE 2
                END,
                table_schema,
                ordinal_position
            """,
            (table_name,),
        )
        rows = cur.fetchall()

    if not rows:
        raise RuntimeError(f"TABLE_NOT_FOUND:{table_name}")

    selected_schema = rows[0][0]
    columns = {column for schema, column in rows if schema == selected_schema}

    return (
        f"{_quote_identifier(selected_schema)}.{_quote_identifier(table_name)}",
        columns,
    )


def _require_columns(table_name: str, columns: set, required: List[str]) -> None:
    missing = [column for column in required if column not in columns]
    if missing:
        raise RuntimeError(
            f"REQUIRED_COLUMNS_MISSING:{table_name}:{','.join(missing)}"
        )


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default

    try:
        return int(value)
    except Exception:
        return default


def load_latest_plan(conn, plan_table: str, plan_date: date) -> Optional[Dict[str, Any]]:
    with _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT
                id,
                plan_date,
                plan_status,
                total_candidate_count,
                ready_order_count,
                blocked_order_count,
                skipped_order_count,
                strategy_name,
                strategy_version,
                market_signal,
                risk_regime,
                created_at,
                updated_at
            FROM {plan_table}
            WHERE plan_date = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (plan_date,),
        )
        row = cur.fetchone()

    return dict(row) if row else None


def load_plan_orders(
    conn,
    order_table: str,
    execution_plan_id: int,
) -> List[Dict[str, Any]]:
    with _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT
                id,
                execution_plan_id,
                execution_mode,
                source_type,
                action_type,
                execution_status,
                ticker_code,
                stock_name,
                order_qty,
                signal_date,
                connector_order_request_id,
                created_at,
                updated_at
            FROM {order_table}
            WHERE execution_plan_id = %s
              AND execution_mode = %s
            ORDER BY id ASC
            """,
            (execution_plan_id, EXECUTION_MODE),
        )
        rows = cur.fetchall()

    return [dict(row) for row in rows]


def validate_ready_plan_order(plan_date: date) -> Tuple[
    Optional[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    with get_conn() as conn:
        conn.autocommit = True

        plan_table, plan_columns = _table_info(
            conn,
            "strategy_execution_plan",
        )
        order_table, order_columns = _table_info(
            conn,
            "strategy_execution_order",
        )

        _require_columns(
            "strategy_execution_plan",
            plan_columns,
            [
                "id",
                "plan_date",
                "plan_status",
                "total_candidate_count",
                "ready_order_count",
            ],
        )
        _require_columns(
            "strategy_execution_order",
            order_columns,
            [
                "id",
                "execution_plan_id",
                "execution_mode",
                "action_type",
                "execution_status",
                "ticker_code",
                "order_qty",
            ],
        )

        plan = load_latest_plan(
            conn=conn,
            plan_table=plan_table,
            plan_date=plan_date,
        )

        if plan is None:
            return None, [], [
                {
                    "code": "EXECUTION_PLAN_NOT_FOUND",
                    "detail": f"plan_date={plan_date}",
                }
            ]

        orders = load_plan_orders(
            conn=conn,
            order_table=order_table,
            execution_plan_id=plan["id"],
        )

        errors: List[Dict[str, Any]] = []

        plan_status = str(plan.get("plan_status") or "").upper()
        total_candidate_count = _to_int(plan.get("total_candidate_count"))
        ready_order_count = _to_int(plan.get("ready_order_count"))
        actual_order_count = len(orders)

        if ready_order_count < 0:
            errors.append(
                {
                    "code": "READY_ORDER_COUNT_NEGATIVE",
                    "detail": f"ready_order_count={ready_order_count}",
                }
            )

        if total_candidate_count < ready_order_count:
            errors.append(
                {
                    "code": "PLAN_COUNT_INCONSISTENT",
                    "detail": (
                        f"total_candidate_count={total_candidate_count}, "
                        f"ready_order_count={ready_order_count}"
                    ),
                }
            )

        if plan_status == "READY" and ready_order_count <= 0:
            errors.append(
                {
                    "code": "READY_PLAN_WITHOUT_READY_ORDER_COUNT",
                    "detail": (
                        f"plan_id={plan['id']}, "
                        f"ready_order_count={ready_order_count}"
                    ),
                }
            )

        if ready_order_count > 0 and actual_order_count == 0:
            errors.append(
                {
                    "code": "READY_PLAN_ORDER_MISSING",
                    "detail": (
                        f"plan_id={plan['id']}, "
                        f"expected={ready_order_count}, actual=0"
                    ),
                }
            )

        if actual_order_count != ready_order_count:
            errors.append(
                {
                    "code": "READY_PLAN_ORDER_COUNT_MISMATCH",
                    "detail": (
                        f"plan_id={plan['id']}, "
                        f"expected={ready_order_count}, "
                        f"actual={actual_order_count}"
                    ),
                }
            )

        for order in orders:
            order_id = order.get("id")
            order_plan_id = order.get("execution_plan_id")
            action_type = str(order.get("action_type") or "").upper()
            ticker_code = str(order.get("ticker_code") or "").strip()
            order_qty = _to_int(order.get("order_qty"))

            if order_plan_id != plan.get("id"):
                errors.append(
                    {
                        "code": "ORDER_PLAN_ID_MISMATCH",
                        "execution_order_id": order_id,
                        "detail": (
                            f"plan_id={plan.get('id')}, "
                            f"order_plan_id={order_plan_id}"
                        ),
                    }
                )

            if action_type not in {"BUY", "SELL"}:
                errors.append(
                    {
                        "code": "ORDER_ACTION_INVALID",
                        "execution_order_id": order_id,
                        "detail": f"action_type={action_type or 'NULL'}",
                    }
                )

            if not ticker_code:
                errors.append(
                    {
                        "code": "ORDER_TICKER_MISSING",
                        "execution_order_id": order_id,
                        "detail": "ticker_code is empty",
                    }
                )

            if order_qty <= 0:
                errors.append(
                    {
                        "code": "ORDER_QTY_INVALID",
                        "execution_order_id": order_id,
                        "detail": f"order_qty={order.get('order_qty')}",
                    }
                )

        return plan, orders, errors


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "plan date must be YYYY-MM-DD"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate READY execution plan -> execution orders"
    )
    parser.add_argument(
        "--plan-date",
        type=_parse_date,
        default=date.today(),
        help="plan date in YYYY-MM-DD; default: local today",
    )
    parser.add_argument(
        "--allow-no-plan",
        action="store_true",
        help="return success when no execution plan exists for the date",
    )
    args = parser.parse_args()

    plan, orders, errors = validate_ready_plan_order(args.plan_date)

    print("========================================")
    print("[READY Plan -> Order Validation]")
    print("========================================")
    print(f"plan_date : {args.plan_date}")

    if plan is None:
        print("plan_id   : None")
        print("order_count : 0")

        if args.allow_no_plan:
            print(
                "READY_PLAN_ORDER_VALIDATION=SUCCESS "
                "reason=NO_PLAN_ALLOWED"
            )
            return 0

        for error in errors:
            print("[ERROR] " + json.dumps(error, ensure_ascii=False))

        print(
            "READY_PLAN_ORDER_VALIDATION=FAILED "
            "reason=EXECUTION_PLAN_NOT_FOUND"
        )
        return 1

    print(f"plan_id               : {plan.get('id')}")
    print(f"plan_status           : {plan.get('plan_status')}")
    print(f"total_candidate_count : {plan.get('total_candidate_count')}")
    print(f"ready_order_count     : {plan.get('ready_order_count')}")
    print(f"actual_order_count    : {len(orders)}")

    for order in orders:
        safe_order = {
            "id": order.get("id"),
            "execution_plan_id": order.get("execution_plan_id"),
            "execution_mode": order.get("execution_mode"),
            "source_type": order.get("source_type"),
            "action_type": order.get("action_type"),
            "execution_status": order.get("execution_status"),
            "ticker_code": order.get("ticker_code"),
            "order_qty": order.get("order_qty"),
            "signal_date": str(order.get("signal_date")),
        }
        print("[ORDER] " + json.dumps(safe_order, ensure_ascii=False))

    for error in errors:
        print("[ERROR] " + json.dumps(error, ensure_ascii=False))

    if errors:
        print(
            "READY_PLAN_ORDER_VALIDATION=FAILED "
            f"plan_id={plan.get('id')} errors={len(errors)}"
        )
        return 1

    print(
        "READY_PLAN_ORDER_VALIDATION=SUCCESS "
        f"plan_id={plan.get('id')} "
        f"expected={plan.get('ready_order_count')} "
        f"actual={len(orders)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
