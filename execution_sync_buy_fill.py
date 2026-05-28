"""
connector BUY 체결 내역을 strategy_execution_order 상태에 동기화하는 entrypoint.
connector_order_request와 connector_fill을 조회하고 BUY order를 FILLED로 갱신할 수 있다.
체결 조회 및 DB update 경로이므로 명시 승인 없이 실행하지 않는다.
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


def get_submitted_buy_orders(conn):
    """
    아직 Strategy 쪽에서 FILLED 처리되지 않은 BUY 주문 조회.

    대상:
    - action_type = BUY
    - execution_status = SUBMITTED
    - connector_order_request_id IS NOT NULL

    source_type은 TRADE_LOG_BUY 중심이지만,
    향후 다른 BUY source_type이 생겨도 action_type 기준으로 동기화 가능하게 둔다.
    """

    sql = """
        SELECT
            id,
            execution_plan_id,
            source_trade_log_id,
            source_run_id,
            source_type,
            execution_mode,
            action_type,
            ticker_code,
            stock_name,
            order_qty,
            order_price,
            execution_status,
            connector_order_request_id,
            result_payload,
            signal_date,
            signal_type,
            signal_score,
            signal_position_size,
            target_amount,
            current_qty,
            current_eval_amount,
            created_at,
            updated_at
        FROM strategy_execution_order
        WHERE action_type = 'BUY'
          AND execution_status = 'SUBMITTED'
          AND connector_order_request_id IS NOT NULL
        ORDER BY id ASC
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
    fill_ids = []

    for fill in fills:
        qty = to_int(fill.get("fill_qty"))
        amount = to_decimal(fill.get("fill_amount"))
        total_qty += qty
        total_amount += amount
        latest_fill_ts = fill.get("fill_ts")
        fill_ids.append(fill.get("id"))

    avg_price = Decimal("0")
    if total_qty > 0:
        avg_price = total_amount / Decimal(total_qty)

    return {
        "fill_ids": fill_ids,
        "total_fill_qty": total_qty,
        "total_fill_amount": total_amount,
        "avg_fill_price": avg_price,
        "latest_fill_ts": latest_fill_ts,
    }


def mark_execution_order_filled(conn, execution_order, order_request, fill_summary):
    """
    strategy_execution_order를 FILLED로 마감.
    기존 result_payload에 sync_result를 추가한다.
    """

    result_payload = execution_order.get("result_payload") or {}

    sync_result = {
        "source": "execution_sync_buy_fill",
        "connector_order_request_id": order_request.get("id"),
        "connector_request_status": order_request.get("request_status"),
        "broker_order_no": order_request.get("broker_order_no"),
        "broker_branch_code": order_request.get("broker_branch_code"),
        "fill_ids": fill_summary["fill_ids"],
        "fill_qty": fill_summary["total_fill_qty"],
        "avg_fill_price": str(fill_summary["avg_fill_price"]),
        "fill_amount": str(fill_summary["total_fill_amount"]),
        "latest_fill_ts": str(fill_summary["latest_fill_ts"]),
    }

    result_payload["sync_result"] = sync_result

    sql = """
        UPDATE strategy_execution_order
        SET
            execution_status = 'FILLED',
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
    """
    SUBMITTED BUY execution order 1건의 connector 체결을 요약해 FILLED 상태로 반영한다.
    connector fill 조회 결과가 후속 position sync의 기준이 된다.
    """
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

    execution_update = mark_execution_order_filled(
        conn=conn,
        execution_order=execution_order,
        order_request=order_request,
        fill_summary=fill_summary,
    )

    return {
        "execution_order_id": execution_order["id"],
        "connector_order_request_id": order_request_id,
        "status": "SYNCED",
        "fill_summary": fill_summary,
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
        orders = get_submitted_buy_orders(conn)

        print_header("[Execution BUY Fill Sync]")
        print(f"submitted_buy_orders : {len(orders)}")

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
            print(f"status                   : {result.get('status')}")

            if result.get("reason"):
                print(f"reason                   : {result.get('reason')}")

            if result.get("fill_summary"):
                fs = result["fill_summary"]
                print(f"fill_ids                 : {fs['fill_ids']}")
                print(f"total_fill_qty           : {fs['total_fill_qty']}")
                print(f"avg_fill_price           : {fs['avg_fill_price']}")
                print(f"total_fill_amount        : {fs['total_fill_amount']}")

    except Exception as e:
        conn.rollback()
        print()
        print("[ERROR] Execution BUY fill sync 실패")
        print(e)
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
