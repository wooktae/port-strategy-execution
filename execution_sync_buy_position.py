"""
FILLED BUY execution order를 strategy_position_state OPEN 포지션으로 동기화한다.
connector 주문/체결 정보를 조회해 포지션 row를 생성하고 execution order payload를 갱신한다.
포지션 생성 DB write가 발생하므로 명시 승인 없이 실행하지 않는다.
"""

from decimal import Decimal

from execution_db import get_conn, fetch_all, fetch_one, execute_one
from execution_repository import dumps_json


def to_decimal(value, default="0"):
    if value is None:
        return Decimal(default)

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def to_int(value, default=0):
    if value is None:
        return default

    try:
        return int(value)
    except Exception:
        return default


def get_filled_buy_execution_orders_without_position(conn):
    """
    FILLED 처리된 BUY execution_order 중
    아직 strategy_position_state가 생성되지 않은 주문 조회.

    기준:
    - action_type = BUY
    - execution_status = FILLED
    - connector_order_request_id IS NOT NULL
    - strategy_position_state.source_buy_execution_order_id 로 중복 방지
    """

    sql = """
        SELECT
            seo.id,
            seo.execution_plan_id,
            seo.source_trade_log_id,
            seo.source_run_id,
            seo.source_type,
            seo.execution_mode,
            seo.action_type,
            seo.ticker_code,
            seo.stock_name,
            seo.order_qty,
            seo.order_price,
            seo.execution_status,
            seo.connector_order_request_id,
            seo.result_payload,
            seo.signal_date,
            seo.signal_type,
            seo.signal_score,
            seo.signal_position_size,
            seo.target_amount,
            seo.current_qty,
            seo.current_eval_amount,
            seo.created_at,
            seo.updated_at
        FROM strategy_execution_order seo
        LEFT JOIN strategy_position_state ps
          ON ps.source_buy_execution_order_id = seo.id
        WHERE seo.action_type = 'BUY'
          AND seo.execution_status = 'FILLED'
          AND seo.connector_order_request_id IS NOT NULL
          AND ps.id IS NULL
        ORDER BY seo.id ASC
    """

    return fetch_all(conn, sql)


def get_connector_order_request(conn, order_request_id):
    sql = """
        SELECT
            id,
            account_id,
            account_no,
            ticker_code,
            stock_name,
            request_type,
            order_method,
            order_qty,
            request_status,
            broker_order_no,
            broker_branch_code,
            requested_at,
            accepted_at,
            last_event_at,
            response_payload
        FROM connector_order_request
        WHERE id = %(order_request_id)s
    """

    return fetch_one(conn, sql, {
        "order_request_id": order_request_id,
    })


def get_connector_buy_fills(conn, order_request_id):
    sql = """
        SELECT
            id,
            order_request_id,
            order_event_id,
            account_id,
            broker_order_no,
            broker_branch_code,
            ticker_code,
            side,
            fill_qty,
            fill_price,
            fill_amount,
            fill_ts,
            raw_json,
            created_at
        FROM connector_fill
        WHERE order_request_id = %(order_request_id)s
          AND side = 'BUY'
        ORDER BY fill_ts ASC, id ASC
    """

    return fetch_all(conn, sql, {
        "order_request_id": order_request_id,
    })


def summarize_fills(fills):
    total_qty = 0
    total_amount = Decimal("0")
    latest_fill_ts = None
    first_fill_ts = None
    fill_ids = []
    first_fill_id = None

    for fill in fills:
        qty = to_int(fill.get("fill_qty"))
        amount = to_decimal(fill.get("fill_amount"))

        total_qty += qty
        total_amount += amount

        fill_ts = fill.get("fill_ts")
        if first_fill_ts is None:
            first_fill_ts = fill_ts
        latest_fill_ts = fill_ts

        fill_id = fill.get("id")
        if first_fill_id is None:
            first_fill_id = fill_id
        fill_ids.append(fill_id)

    avg_price = Decimal("0")
    if total_qty > 0:
        avg_price = total_amount / Decimal(total_qty)

    return {
        "fill_ids": fill_ids,
        "first_fill_id": first_fill_id,
        "total_fill_qty": total_qty,
        "total_fill_amount": total_amount,
        "avg_fill_price": avg_price,
        "first_fill_ts": first_fill_ts,
        "latest_fill_ts": latest_fill_ts,
    }


def build_buy_info(execution_order, order_request, fill_summary):
    return {
        "source": "execution_sync_buy_position",
        "execution_order_id": execution_order.get("id"),
        "execution_plan_id": execution_order.get("execution_plan_id"),
        "source_type": execution_order.get("source_type"),
        "execution_mode": execution_order.get("execution_mode"),
        "source_trade_log_id": execution_order.get("source_trade_log_id"),
        "source_run_id": execution_order.get("source_run_id"),
        "connector_order_request_id": order_request.get("id"),
        "connector_request_status": order_request.get("request_status"),
        "broker_order_no": order_request.get("broker_order_no"),
        "broker_branch_code": order_request.get("broker_branch_code"),
        "fill_ids": fill_summary["fill_ids"],
        "entry_qty": fill_summary["total_fill_qty"],
        "entry_price": str(fill_summary["avg_fill_price"]),
        "entry_amount": str(fill_summary["total_fill_amount"]),
        "entry_ts": str(fill_summary["first_fill_ts"]),
        "signal_date": str(execution_order.get("signal_date")),
        "signal_type": execution_order.get("signal_type"),
        "signal_score": str(execution_order.get("signal_score")),
        "signal_position_size": str(execution_order.get("signal_position_size")),
        "target_amount": str(execution_order.get("target_amount")),
    }


def create_position_state(conn, execution_order, order_request, fill_summary):
    """
    BUY fill 기준으로 strategy_position_state OPEN 생성.

    중복 방지:
    - source_buy_execution_order_id 기준 NOT EXISTS
    - UNIQUE 제약이 없어도 논리적으로 중복 생성 방지
    """

    buy_info = build_buy_info(
        execution_order=execution_order,
        order_request=order_request,
        fill_summary=fill_summary,
    )

    first_fill_ts = fill_summary["first_fill_ts"]
    entry_date = None

    if first_fill_ts is not None:
        entry_date = first_fill_ts.date()

    account_id = order_request.get("account_id")
    account_no = order_request.get("account_no")
    ticker_code = order_request.get("ticker_code") or execution_order.get("ticker_code")
    stock_name = order_request.get("stock_name") or execution_order.get("stock_name")

    sql = """
        INSERT INTO strategy_position_state (
            account_id,
            account_no,
            ticker_code,
            stock_name,
            source_buy_execution_order_id,
            source_connector_order_request_id,
            source_connector_fill_id,
            entry_date,
            entry_price,
            entry_qty,
            remaining_qty,
            position_status,
            buy_info,
            memo,
            created_at,
            updated_at
        )
        SELECT
            %(account_id)s,
            %(account_no)s,
            %(ticker_code)s,
            %(stock_name)s,
            %(source_buy_execution_order_id)s,
            %(source_connector_order_request_id)s,
            %(source_connector_fill_id)s,
            %(entry_date)s,
            %(entry_price)s,
            %(entry_qty)s,
            %(remaining_qty)s,
            'OPEN',
            %(buy_info)s::jsonb,
            %(memo)s,
            now(),
            now()
        WHERE NOT EXISTS (
            SELECT 1
            FROM strategy_position_state
            WHERE source_buy_execution_order_id = %(source_buy_execution_order_id)s
        )
        RETURNING
            id,
            account_no,
            ticker_code,
            stock_name,
            source_buy_execution_order_id,
            source_connector_order_request_id,
            source_connector_fill_id,
            entry_date,
            entry_price,
            entry_qty,
            remaining_qty,
            position_status,
            buy_info,
            created_at,
            updated_at
    """

    return execute_one(conn, sql, {
        "account_id": account_id,
        "account_no": account_no,
        "ticker_code": ticker_code,
        "stock_name": stock_name,
        "source_buy_execution_order_id": execution_order.get("id"),
        "source_connector_order_request_id": order_request.get("id"),
        "source_connector_fill_id": fill_summary["first_fill_id"],
        "entry_date": entry_date,
        "entry_price": fill_summary["avg_fill_price"],
        "entry_qty": fill_summary["total_fill_qty"],
        "remaining_qty": fill_summary["total_fill_qty"],
        "buy_info": dumps_json(buy_info),
        "memo": "Created from FILLED BUY execution order by execution_sync_buy_position",
    })


def append_position_sync_result(conn, execution_order, position_state):
    """
    strategy_execution_order.result_payload에 position_sync_result를 추가.
    """

    result_payload = execution_order.get("result_payload") or {}

    position_sync_result = {
        "source": "execution_sync_buy_position",
        "position_state_id": position_state.get("id") if position_state else None,
        "position_status": position_state.get("position_status") if position_state else None,
        "entry_date": str(position_state.get("entry_date")) if position_state else None,
        "entry_price": str(position_state.get("entry_price")) if position_state else None,
        "entry_qty": position_state.get("entry_qty") if position_state else None,
        "remaining_qty": position_state.get("remaining_qty") if position_state else None,
    }

    result_payload["position_sync_result"] = position_sync_result

    sql = """
        UPDATE strategy_execution_order
        SET
            result_payload = %(result_payload)s::jsonb,
            updated_at = now()
        WHERE id = %(execution_order_id)s
        RETURNING
            id,
            execution_status,
            connector_order_request_id,
            result_payload,
            updated_at
    """

    return execute_one(conn, sql, {
        "execution_order_id": execution_order["id"],
        "result_payload": dumps_json(result_payload),
    })


def sync_one_order(conn, execution_order):
    order_request_id = execution_order.get("connector_order_request_id")

    order_request = get_connector_order_request(
        conn=conn,
        order_request_id=order_request_id,
    )

    if not order_request:
        return {
            "execution_order_id": execution_order["id"],
            "status": "SKIP",
            "reason": "CONNECTOR_ORDER_REQUEST_NOT_FOUND",
        }

    if order_request.get("request_status") != "FILLED":
        return {
            "execution_order_id": execution_order["id"],
            "connector_order_request_id": order_request_id,
            "status": "SKIP",
            "reason": f"CONNECTOR_ORDER_NOT_FILLED:{order_request.get('request_status')}",
        }

    fills = get_connector_buy_fills(
        conn=conn,
        order_request_id=order_request_id,
    )

    if not fills:
        return {
            "execution_order_id": execution_order["id"],
            "connector_order_request_id": order_request_id,
            "status": "SKIP",
            "reason": "BUY_FILL_NOT_FOUND",
        }

    fill_summary = summarize_fills(fills)

    if fill_summary["total_fill_qty"] <= 0:
        return {
            "execution_order_id": execution_order["id"],
            "connector_order_request_id": order_request_id,
            "status": "SKIP",
            "reason": "TOTAL_FILL_QTY_ZERO",
        }

    position_state = create_position_state(
        conn=conn,
        execution_order=execution_order,
        order_request=order_request,
        fill_summary=fill_summary,
    )

    if not position_state:
        return {
            "execution_order_id": execution_order["id"],
            "connector_order_request_id": order_request_id,
            "status": "SKIP",
            "reason": "POSITION_ALREADY_EXISTS_OR_INSERT_SKIPPED",
        }

    execution_update = append_position_sync_result(
        conn=conn,
        execution_order=execution_order,
        position_state=position_state,
    )

    return {
        "execution_order_id": execution_order["id"],
        "connector_order_request_id": order_request_id,
        "position_state_id": position_state.get("id"),
        "status": "SYNCED",
        "position_state": position_state,
        "execution_update": execution_update,
    }


def print_header(title):
    print()
    print("========================================")
    print(title)
    print("========================================")


def main():
    conn = get_conn()
    conn.autocommit = False

    try:
        orders = get_filled_buy_execution_orders_without_position(conn)

        print_header("[Execution BUY Position Sync]")
        print(f"filled_buy_orders_without_position : {len(orders)}")

        synced_count = 0
        skipped_count = 0
        results = []

        for order in orders:
            result = sync_one_order(conn, order)
            results.append(result)

            if result["status"] == "SYNCED":
                synced_count += 1
            else:
                skipped_count += 1

        conn.commit()

        print(f"synced_count  : {synced_count}")
        print(f"skipped_count : {skipped_count}")

        for result in results:
            print()
            print("----------------------------------------")
            print(f"execution_order_id       : {result.get('execution_order_id')}")
            print(f"connector_order_request  : {result.get('connector_order_request_id')}")
            print(f"position_state_id        : {result.get('position_state_id')}")
            print(f"status                   : {result.get('status')}")

            if result.get("reason"):
                print(f"reason                   : {result.get('reason')}")

            if result.get("position_state"):
                ps = result["position_state"]
                print(f"ticker_code              : {ps.get('ticker_code')}")
                print(f"stock_name               : {ps.get('stock_name')}")
                print(f"entry_date               : {ps.get('entry_date')}")
                print(f"entry_price              : {ps.get('entry_price')}")
                print(f"entry_qty                : {ps.get('entry_qty')}")
                print(f"remaining_qty            : {ps.get('remaining_qty')}")
                print(f"position_status          : {ps.get('position_status')}")

    except Exception as e:
        conn.rollback()
        print()
        print("[ERROR] Execution BUY position sync 실패")
        print(e)
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
