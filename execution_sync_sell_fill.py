from decimal import Decimal

from execution_db import get_conn, fetch_all, fetch_one, execute_one
from execution_repository import dumps_json


SYNC_SOURCE = "execution_sync_sell_fill"


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


def get_submitted_position_sell_orders(conn):
    """
    아직 Strategy 쪽에서 FILLED/CLOSED 처리되지 않은 POSITION_SELL 주문 조회.
    """

    sql = """
        SELECT
            id,
            execution_plan_id,
            source_position_state_id,
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
            sell_reason,
            sell_info,
            expected_sell_price,
            expected_pnl_amount,
            expected_pnl_rate,
            created_at,
            updated_at
        FROM strategy_execution_order
        WHERE source_type IN ('POSITION_SELL', 'DAILY_POSITION_SELL', 'INTRADAY_STOP_SELL')
            AND action_type = 'SELL'
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


def get_connector_sell_fills(conn, order_request_id):
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
          AND side = 'SELL'
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


def build_sell_sync_result(order_request, fill_summary):
    return {
        "source": SYNC_SOURCE,
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


def build_close_result(fill_summary):
    return {
        "source": SYNC_SOURCE,
        "fill_ids": fill_summary["fill_ids"],
        "closed_qty": fill_summary["total_fill_qty"],
        "avg_fill_price": str(fill_summary["avg_fill_price"]),
        "fill_amount": str(fill_summary["total_fill_amount"]),
        "latest_fill_ts": str(fill_summary["latest_fill_ts"]),
    }


def mark_execution_order_filled(conn, execution_order, order_request, fill_summary):
    """
    strategy_execution_order를 FILLED로 마감.
    기존 result_payload에 sync_result를 추가한다.
    """

    result_payload = execution_order.get("result_payload") or {}
    result_payload["sync_result"] = build_sell_sync_result(
        order_request=order_request,
        fill_summary=fill_summary,
    )

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


def close_position_after_sell_fill(conn, execution_order, fill_summary):
    """
    strategy_position_state의 remaining_qty를 체결 수량만큼 차감한다.

    보정 포인트:
    - SELL 체결로 CLOSED 처리되는 경우 latest_sell_reason을 SELL 주문 기준으로 덮어쓴다.
    - latest_validation_result의 action/reason/detail도 SELL 기준으로 덮어쓴다.
    - 기존 HOLD_MIN_HOLDING_DAYS 같은 이전 평가 결과가 CLOSED 포지션에 남지 않도록 한다.
    """

    close_result = build_close_result(fill_summary)

    sql = """
        UPDATE strategy_position_state ps
        SET
            remaining_qty = GREATEST(ps.remaining_qty - %(closed_qty)s, 0),

            position_status =
                CASE
                    WHEN GREATEST(ps.remaining_qty - %(closed_qty)s, 0) <= 0
                        THEN 'CLOSED'
                    ELSE 'OPEN'
                END,

            latest_sell_reason = COALESCE(
                seo.sell_reason,
                seo.sell_info ->> 'reason',
                'SELL_FILLED'
            ),

            latest_validation_result =
                COALESCE(ps.latest_validation_result, '{}'::jsonb)
                || jsonb_build_object(
                    'action', 'SELL',
                    'reason', COALESCE(
                        seo.sell_reason,
                        seo.sell_info ->> 'reason',
                        'SELL_FILLED'
                    ),
                    'detail', COALESCE(
                        seo.sell_info ->> 'detail',
                        'SELL fill synced and position closed'
                    ),
                    'order_qty', seo.order_qty,
                    'expected_sell_price', seo.expected_sell_price,
                    'expected_pnl_amount', seo.expected_pnl_amount,
                    'expected_pnl_rate', seo.expected_pnl_rate,
                    'sell_execution_order_id', seo.id,
                    'connector_order_request_id', seo.connector_order_request_id,
                    'sync_close_result', %(close_result)s::jsonb
                ),

            updated_at = now()
        FROM strategy_execution_order seo
        WHERE ps.id = seo.source_position_state_id
          AND ps.id = %(position_state_id)s
          AND seo.id = %(execution_order_id)s
          AND seo.source_type IN ('POSITION_SELL', 'DAILY_POSITION_SELL', 'INTRADAY_STOP_SELL')
          AND seo.action_type = 'SELL'
        RETURNING
            ps.id,
            ps.ticker_code,
            ps.stock_name,
            ps.remaining_qty,
            ps.position_status,
            ps.latest_sell_reason,
            ps.latest_validation_result,
            ps.updated_at
    """

    return execute_one(conn, sql, {
        "position_state_id": execution_order["source_position_state_id"],
        "execution_order_id": execution_order["id"],
        "closed_qty": fill_summary["total_fill_qty"],
        "close_result": dumps_json(close_result),
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

    fills = get_connector_sell_fills(
        conn=conn,
        order_request_id=order_request_id,
    )

    if not fills:
        return {
            "execution_order_id": execution_order["id"],
            "connector_order_request_id": order_request_id,
            "status": "SKIP",
            "reason": "SELL_FILL_NOT_FOUND",
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

    position_update = None
    if execution_order.get("source_position_state_id"):
        position_update = close_position_after_sell_fill(
            conn=conn,
            execution_order=execution_order,
            fill_summary=fill_summary,
        )

    return {
        "execution_order_id": execution_order["id"],
        "connector_order_request_id": order_request_id,
        "position_state_id": execution_order.get("source_position_state_id"),
        "status": "SYNCED",
        "fill_summary": fill_summary,
        "execution_update": execution_update,
        "position_update": position_update,
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
        orders = get_submitted_position_sell_orders(conn)

        print_header("[Execution SELL Fill Sync]")
        print(f"submitted_position_sell_orders : {len(orders)}")

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

            if result.get("fill_summary"):
                fs = result["fill_summary"]
                print(f"fill_ids                 : {fs['fill_ids']}")
                print(f"total_fill_qty           : {fs['total_fill_qty']}")
                print(f"avg_fill_price           : {fs['avg_fill_price']}")
                print(f"total_fill_amount        : {fs['total_fill_amount']}")

    except Exception as e:
        conn.rollback()
        print()
        print("[ERROR] Execution SELL fill sync 실패")
        print(e)
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
