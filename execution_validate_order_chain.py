"""
Validate the paper strategy execution chain after Step 16.

Validation chain:
strategy_execution_plan
  -> strategy_execution_order
  -> connector_order_request
  -> connector_fill
  -> strategy_position_state

This script is read-only. It never inserts, updates, or deletes DB rows.
Any inconsistency causes a non-zero exit code so Step Functions can fail safely.
"""

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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
FILLED_ORDER_STATUS = "FILLED"
CANCELED_ORDER_STATUSES = {
    "CANCELED",
    "CANCELLED",
}
CANCELED_REQUEST_STATUSES = {
    "CANCELED",
    "CANCELLED",
}
ACTIVE_REQUEST_STATUSES = {
    "ACCEPTED",
    "SUBMITTED",
    "PENDING",
    "PARTIAL_FILLED",
    "PARTIALLY_FILLED",
}
TERMINAL_REQUEST_STATUSES = {
    "FILLED",
    "REJECTED",
    "CANCELED",
    "CANCELLED",
    "FAILED",
}


def _dict_cursor(conn):
    """
    Creates a cursor so that dict-shaped rows can be received consistently,
    whether execution_db.get_conn() returns a psycopg3 or a psycopg2 connection.
    """
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


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


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
    table_ref = (
        f"{_quote_identifier(selected_schema)}.{_quote_identifier(table_name)}"
    )
    return table_ref, columns


def _require_columns(
    table_name: str,
    columns: Iterable[str],
    required: Sequence[str],
) -> None:
    missing = [column for column in required if column not in columns]
    if missing:
        raise RuntimeError(
            f"REQUIRED_COLUMNS_MISSING:{table_name}:{','.join(missing)}"
        )


def _build_order_date_condition(
    order_columns: set,
    run_date: date,
) -> Tuple[str, List[Any]]:
    if "signal_date" in order_columns:
        return "eo.signal_date = %s", [run_date]

    if "created_at" in order_columns:
        return "eo.created_at::date = %s", [run_date]

    raise RuntimeError(
        "ORDER_DATE_COLUMN_NOT_FOUND:strategy_execution_order:"
        "signal_date_or_created_at"
    )


def _load_orders(
    conn,
    order_table: str,
    order_columns: set,
    run_date: date,
    plan_id: Optional[int],
) -> List[Dict[str, Any]]:
    required = [
        "id",
        "execution_plan_id",
        "execution_mode",
        "action_type",
        "execution_status",
        "ticker_code",
        "order_qty",
        "connector_order_request_id",
    ]
    _require_columns("strategy_execution_order", order_columns, required)

    optional_columns = [
        "source_type",
        "stock_name",
        "source_position_state_id",
        "result_payload",
        "signal_date",
        "created_at",
        "updated_at",
    ]

    select_parts = [f"eo.{column}" for column in required]
    for column in optional_columns:
        if column in order_columns and column not in required:
            select_parts.append(f"eo.{column}")
        elif column not in order_columns:
            select_parts.append(f"NULL AS {column}")

    conditions = [
        "eo.execution_mode = %s",
        "eo.action_type IN ('BUY', 'SELL')",
    ]
    params: List[Any] = [EXECUTION_MODE]

    date_condition, date_params = _build_order_date_condition(
        order_columns=order_columns,
        run_date=run_date,
    )
    conditions.append(date_condition)
    params.extend(date_params)

    if plan_id is not None:
        conditions.append("eo.execution_plan_id = %s")
        params.append(plan_id)

    sql = f"""
        SELECT
            {", ".join(select_parts)}
        FROM {order_table} eo
        WHERE {" AND ".join(conditions)}
        ORDER BY eo.id ASC
    """

    with _dict_cursor(conn) as cur:
        cur.execute(sql, tuple(params))
        return [dict(row) for row in cur.fetchall()]


def _fetch_one_by_id(
    conn,
    table_ref: str,
    row_id: Any,
) -> Optional[Dict[str, Any]]:
    if row_id is None:
        return None

    with _dict_cursor(conn) as cur:
        cur.execute(
            f"SELECT * FROM {table_ref} WHERE id = %s",
            (row_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _load_fills(
    conn,
    fill_table: str,
    order_request_id: int,
) -> List[Dict[str, Any]]:
    with _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT *
            FROM {fill_table}
            WHERE order_request_id = %s
            ORDER BY fill_ts ASC NULLS LAST, id ASC
            """,
            (order_request_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def _load_position_by_buy_order(
    conn,
    position_table: str,
    execution_order_id: int,
    order_request_id: int,
) -> Optional[Dict[str, Any]]:
    with _dict_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT *
            FROM {position_table} ps
            WHERE ps.source_buy_execution_order_id = %s
               OR ps.source_connector_order_request_id = %s
               OR ps.buy_info ->> 'execution_order_id' = %s
               OR ps.buy_info ->> 'connector_order_request_id' = %s
               OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(
                        COALESCE(ps.buy_info -> 'additional_buys', '[]'::jsonb)
                    ) add_buy
                    WHERE add_buy ->> 'execution_order_id' = %s
                       OR add_buy ->> 'connector_order_request_id' = %s
               )
            ORDER BY ps.id ASC
            LIMIT 1
            """,
            (
                execution_order_id,
                order_request_id,
                str(execution_order_id),
                str(order_request_id),
                str(execution_order_id),
                str(order_request_id),
            ),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _add_error(
    errors: List[Dict[str, Any]],
    order: Dict[str, Any],
    code: str,
    detail: str,
) -> None:
    errors.append(
        {
            "execution_order_id": order.get("id"),
            "execution_plan_id": order.get("execution_plan_id"),
            "action_type": order.get("action_type"),
            "ticker_code": order.get("ticker_code"),
            "code": code,
            "detail": detail,
        }
    )


def _validate_order(
    conn,
    order: Dict[str, Any],
    plan_table: str,
    request_table: str,
    fill_table: str,
    position_table: str,
) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []

    order_id = order.get("id")
    plan_id = order.get("execution_plan_id")
    action_type = str(order.get("action_type") or "").upper()
    execution_status = str(
        order.get("execution_status") or ""
    ).upper()
    ticker_code = str(order.get("ticker_code") or "")
    order_qty = _to_int(order.get("order_qty"))
    request_id = order.get("connector_order_request_id")

    if plan_id is None:
        _add_error(
            errors,
            order,
            "EXECUTION_PLAN_ID_MISSING",
            "order has no plan id",
        )
    elif _fetch_one_by_id(conn, plan_table, plan_id) is None:
        _add_error(
            errors,
            order,
            "EXECUTION_PLAN_NOT_FOUND",
            f"execution_plan_id={plan_id}",
        )

    if order_qty <= 0:
        _add_error(
            errors,
            order,
            "ORDER_QTY_INVALID",
            f"order_qty={order.get('order_qty')}",
        )

    valid_execution_statuses = (
        {FILLED_ORDER_STATUS}
        | CANCELED_ORDER_STATUSES
    )

    if execution_status not in valid_execution_statuses:
        _add_error(
            errors,
            order,
            "EXECUTION_ORDER_NOT_TERMINAL",
            (
                "execution_status="
                f"{execution_status or 'NULL'}"
            ),
        )

    if request_id is None:
        _add_error(
            errors,
            order,
            "CONNECTOR_ORDER_REQUEST_ID_MISSING",
            "terminal order has no connector_order_request_id",
        )
        return errors

    request = _fetch_one_by_id(
        conn,
        request_table,
        request_id,
    )

    if request is None:
        _add_error(
            errors,
            order,
            "CONNECTOR_ORDER_REQUEST_NOT_FOUND",
            f"connector_order_request_id={request_id}",
        )
        return errors

    request_type = str(
        request.get("request_type") or ""
    ).upper()
    request_status = str(
        request.get("request_status") or ""
    ).upper()
    request_ticker = str(
        request.get("ticker_code") or ""
    )
    request_qty = _to_int(request.get("order_qty"))

    if request_type != action_type:
        _add_error(
            errors,
            order,
            "ORDER_REQUEST_ACTION_MISMATCH",
            f"order={action_type}, request={request_type}",
        )

    if request_ticker != ticker_code:
        _add_error(
            errors,
            order,
            "ORDER_REQUEST_TICKER_MISMATCH",
            f"order={ticker_code}, request={request_ticker}",
        )

    if request_qty != order_qty:
        _add_error(
            errors,
            order,
            "ORDER_REQUEST_QTY_MISMATCH",
            f"order={order_qty}, request={request_qty}",
        )

    fills = _load_fills(
        conn=conn,
        fill_table=fill_table,
        order_request_id=request_id,
    )

    # -------------------------------------------------
    # 1. Normal cancellation chain
    # -------------------------------------------------
    if execution_status in CANCELED_ORDER_STATUSES:
        if request_status not in CANCELED_REQUEST_STATUSES:
            _add_error(
                errors,
                order,
                "CANCELED_ORDER_REQUEST_STATUS_MISMATCH",
                (
                    f"execution_status={execution_status}, "
                    f"request_status={request_status or 'NULL'}"
                ),
            )

        if fills:
            fill_qty = sum(
                _to_int(fill.get("fill_qty"))
                for fill in fills
            )
            _add_error(
                errors,
                order,
                "CANCELED_ORDER_HAS_FILL",
                (
                    f"connector_order_request_id={request_id}, "
                    f"fill_count={len(fills)}, "
                    f"fill_qty={fill_qty}"
                ),
            )

        if action_type == "BUY":
            position = _load_position_by_buy_order(
                conn=conn,
                position_table=position_table,
                execution_order_id=order_id,
                order_request_id=request_id,
            )

            if position is not None:
                _add_error(
                    errors,
                    order,
                    "CANCELED_BUY_HAS_POSITION_TRACE",
                    (
                        "canceled BUY must not create "
                        "strategy_position_state"
                    ),
                )

        return errors

    # -------------------------------------------------
    # 2. Normal fill chain
    # -------------------------------------------------
    if request_status in ACTIVE_REQUEST_STATUSES:
        _add_error(
            errors,
            order,
            "CONNECTOR_REQUEST_STILL_ACTIVE",
            f"request_status={request_status}",
        )
    elif request_status != "FILLED":
        state_class = (
            "terminal"
            if request_status in TERMINAL_REQUEST_STATUSES
            else "unknown"
        )
        _add_error(
            errors,
            order,
            "CONNECTOR_REQUEST_NOT_FILLED",
            (
                f"request_status={request_status or 'NULL'}, "
                f"class={state_class}"
            ),
        )

    if not fills:
        _add_error(
            errors,
            order,
            "CONNECTOR_FILL_NOT_FOUND",
            f"connector_order_request_id={request_id}",
        )
        return errors

    fill_qty = sum(
        _to_int(fill.get("fill_qty"))
        for fill in fills
    )
    fill_sides = {
        str(fill.get("side") or "").upper()
        for fill in fills
        if fill.get("side") is not None
    }
    fill_tickers = {
        str(fill.get("ticker_code") or "")
        for fill in fills
        if fill.get("ticker_code") is not None
    }

    if fill_qty != order_qty:
        _add_error(
            errors,
            order,
            "ORDER_FILL_QTY_MISMATCH",
            f"order={order_qty}, fills={fill_qty}",
        )

    if fill_sides and fill_sides != {action_type}:
        _add_error(
            errors,
            order,
            "ORDER_FILL_SIDE_MISMATCH",
            (
                f"order={action_type}, "
                f"fills={sorted(fill_sides)}"
            ),
        )

    if fill_tickers and fill_tickers != {ticker_code}:
        _add_error(
            errors,
            order,
            "ORDER_FILL_TICKER_MISMATCH",
            (
                f"order={ticker_code}, "
                f"fills={sorted(fill_tickers)}"
            ),
        )

    if action_type == "BUY":
        position = _load_position_by_buy_order(
            conn=conn,
            position_table=position_table,
            execution_order_id=order_id,
            order_request_id=request_id,
        )

        if position is None:
            _add_error(
                errors,
                order,
                "BUY_POSITION_NOT_FOUND",
                "no strategy_position_state trace for BUY order",
            )
        else:
            position_ticker = str(
                position.get("ticker_code") or ""
            )

            if position_ticker != ticker_code:
                _add_error(
                    errors,
                    order,
                    "BUY_POSITION_TICKER_MISMATCH",
                    (
                        f"order={ticker_code}, "
                        f"position={position_ticker}"
                    ),
                )

            entry_qty = _to_int(
                position.get("entry_qty")
            )
            remaining_qty = _to_int(
                position.get("remaining_qty")
            )

            if entry_qty <= 0:
                _add_error(
                    errors,
                    order,
                    "BUY_POSITION_ENTRY_QTY_INVALID",
                    f"entry_qty={entry_qty}",
                )

            if (
                remaining_qty < 0
                or remaining_qty > entry_qty
            ):
                _add_error(
                    errors,
                    order,
                    "BUY_POSITION_REMAINING_QTY_INVALID",
                    (
                        f"remaining={remaining_qty}, "
                        f"entry={entry_qty}"
                    ),
                )

    if action_type == "SELL":
        position_id = order.get(
            "source_position_state_id"
        )

        if position_id is None:
            _add_error(
                errors,
                order,
                "SELL_SOURCE_POSITION_ID_MISSING",
                "SELL order has no source_position_state_id",
            )
        else:
            position = _fetch_one_by_id(
                conn,
                position_table,
                position_id,
            )

            if position is None:
                _add_error(
                    errors,
                    order,
                    "SELL_SOURCE_POSITION_NOT_FOUND",
                    f"source_position_state_id={position_id}",
                )
            else:
                position_ticker = str(
                    position.get("ticker_code") or ""
                )

                if position_ticker != ticker_code:
                    _add_error(
                        errors,
                        order,
                        "SELL_POSITION_TICKER_MISMATCH",
                        (
                            f"order={ticker_code}, "
                            f"position={position_ticker}"
                        ),
                    )

                remaining_qty = _to_int(
                    position.get("remaining_qty")
                )

                if remaining_qty < 0:
                    _add_error(
                        errors,
                        order,
                        "SELL_POSITION_REMAINING_QTY_NEGATIVE",
                        f"remaining_qty={remaining_qty}",
                    )

    return errors



def validate_chain(
    run_date: date,
    plan_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    with get_conn() as conn:
        conn.autocommit = True

        plan_table, plan_columns = _table_info(conn, "strategy_execution_plan")
        order_table, order_columns = _table_info(conn, "strategy_execution_order")
        request_table, request_columns = _table_info(conn, "connector_order_request")
        fill_table, fill_columns = _table_info(conn, "connector_fill")
        position_table, position_columns = _table_info(conn, "strategy_position_state")

        _require_columns("strategy_execution_plan", plan_columns, ["id"])
        _require_columns(
            "connector_order_request",
            request_columns,
            [
                "id",
                "request_type",
                "order_qty",
                "request_status",
                "ticker_code",
            ],
        )
        _require_columns(
            "connector_fill",
            fill_columns,
            ["id", "order_request_id", "ticker_code", "side", "fill_qty"],
        )
        _require_columns(
            "strategy_position_state",
            position_columns,
            [
                "id",
                "ticker_code",
                "entry_qty",
                "remaining_qty",
                "buy_info",
                "source_buy_execution_order_id",
                "source_connector_order_request_id",
            ],
        )

        orders = _load_orders(
            conn=conn,
            order_table=order_table,
            order_columns=order_columns,
            run_date=run_date,
            plan_id=plan_id,
        )

        errors: List[Dict[str, Any]] = []
        for order in orders:
            errors.extend(
                _validate_order(
                    conn=conn,
                    order=order,
                    plan_table=plan_table,
                    request_table=request_table,
                    fill_table=fill_table,
                    position_table=position_table,
                )
            )

        return orders, errors


def _parse_run_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "run date must be YYYY-MM-DD"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Plan -> Order -> Request -> Fill -> Position chain"
    )
    parser.add_argument(
        "--run-date",
        type=_parse_run_date,
        default=date.today(),
        help="validation date in YYYY-MM-DD; default: local today",
    )
    parser.add_argument(
        "--plan-id",
        type=int,
        default=None,
        help="optional execution plan id filter",
    )
    parser.add_argument(
        "--allow-no-target",
        action="store_true",
        help="return success when no execution orders exist for the date",
    )
    args = parser.parse_args()

    orders, errors = validate_chain(
        run_date=args.run_date,
        plan_id=args.plan_id,
    )

    print("========================================")
    print("[Execution Order Chain Validation]")
    print("========================================")
    print(f"run_date     : {args.run_date}")
    print(f"plan_id      : {args.plan_id}")
    print(f"target_count : {len(orders)}")
    print(f"error_count  : {len(errors)}")

    if not orders and not args.allow_no_target:
        print(
            "ORDER_CHAIN_VALIDATION=FAILED "
            "reason=NO_EXECUTION_ORDER_TARGET"
        )
        return 1

    for order in orders:
        safe_order = {
            key: _json_value(value)
            for key, value in order.items()
            if key not in {"result_payload"}
        }
        print("[ORDER] " + json.dumps(safe_order, ensure_ascii=False))

    for error in errors:
        print("[ERROR] " + json.dumps(error, ensure_ascii=False))

    if errors:
        print(
            "ORDER_CHAIN_VALIDATION=FAILED "
            f"target={len(orders)} errors={len(errors)}"
        )
        return 1

    print(
        "ORDER_CHAIN_VALIDATION=SUCCESS "
        f"target={len(orders)} errors=0"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
