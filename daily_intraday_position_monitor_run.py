"""
Monitor entrypoint that performs intraday checks on OPEN strategy positions and judges stop-loss candidates.
It has paths for connector real-time current-price lookup, storing intraday check results, and creating INTRADAY_STOP_SELL orders.
Because external API lookups and DB writes are possible, do not run it without explicit approval.
"""

import argparse
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from execution_db import get_conn
from execution_repository import (
    dumps_json,
    get_account,
    get_open_strategy_positions_for_intraday_monitor,
    get_latest_connector_position_snapshot,
    get_latest_daily_execution_plan,
    upsert_intraday_stop_sell_execution_order,
    insert_intraday_position_check,
)
from execution_locale import t
# -------------------------------------------------
# Market Connector import path
# -------------------------------------------------
CONNECTOR_PATH = Path(r"C:\Workspaces\port-marketconnector").resolve()

if not CONNECTOR_PATH.exists():
    raise RuntimeError(f"Market Connector 경로가 없음: {CONNECTOR_PATH}")

sys.path.insert(0, str(CONNECTOR_PATH))

try:
    from connector_quote_realtime import get_stock_price  # noqa: E402
except ModuleNotFoundError as e:
    print("[IMPORT ERROR]")
    print(f"CONNECTOR_PATH = {CONNECTOR_PATH}")
    print(f"sys.path[0]    = {sys.path[0]}")
    print(t("Check that connector_quote_realtime.py exists under C:\\Workspaces\\port-marketconnector", "connector_quote_realtime.py 파일이 C:\\Workspaces\\port-marketconnector 아래에 있는지 확인 필요"))
    raise e


SOURCE = "daily_intraday_position_monitor_run"
DEFAULT_HARD_STOP_RATE = Decimal("-0.10")


def print_header(title):
    print()
    print("========================================")
    print(title)
    print("========================================")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Intraday monitor for OPEN strategy positions"
    )

    parser.add_argument(
        "--hard-stop-rate",
        required=False,
        default="-0.10",
        help="entry_price 대비 손절 기준. 기본값 -0.10",
    )

    parser.add_argument(
        "--limit",
        required=False,
        type=int,
        default=50,
        help="점검 대상 최대 건수",
    )

    parser.add_argument(
        "--create-order",
        action="store_true",
        help="장중 손절 조건 충족 시 INTRADAY_STOP_SELL READY 주문 생성",
    )

    return parser.parse_args()


def to_decimal(value, default="0"):
    if value is None:
        return Decimal(default)

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return Decimal(default)


def to_int(value, default=0):
    if value is None:
        return default

    try:
        return int(value)
    except Exception:
        return default


def quantize_rate(value):
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def extract_current_price(quote_result):
    """
    Extract the current price from the return value of connector_quote_realtime.get_stock_price().

    connector_quote_realtime.py returns a current_price- or price-like value based on the KIS output.
    Considering version differences, several keys are treated as fallbacks.
    """

    if not quote_result:
        return Decimal("0")

    candidate_keys = [
        "current_price",
        "price",
        "stck_prpr",
        "prpr",
    ]

    for key in candidate_keys:
        value = quote_result.get(key)
        if value not in (None, "", " "):
            price = to_decimal(value)
            if price > 0:
                return price

    output = quote_result.get("output") or {}
    for key in candidate_keys:
        value = output.get(key)
        if value not in (None, "", " "):
            price = to_decimal(value)
            if price > 0:
                return price

    return Decimal("0")


def extract_previous_close(quote_result):
    """
    Extract the previous close.
    If absent, treat it as 0.
    """

    if not quote_result:
        return Decimal("0")

    candidate_keys = [
        "previous_close",
        "prev_close",
        "stck_sdpr",
        "base_price",
    ]

    for key in candidate_keys:
        value = quote_result.get(key)
        if value not in (None, "", " "):
            price = to_decimal(value)
            if price > 0:
                return price

    output = quote_result.get("output") or {}
    for key in candidate_keys:
        value = output.get(key)
        if value not in (None, "", " "):
            price = to_decimal(value)
            if price > 0:
                return price

    return Decimal("0")


def calculate_rate(current_price, base_price):
    if base_price is None or base_price <= 0:
        return None

    return quantize_rate((current_price - base_price) / base_price)


def build_monitor_result(position, connector_snapshot, quote_result, hard_stop_rate):
    """
    Combine the position, connector snapshot, and current-price response to build the intraday check result.
    It computes whether to stop out and any warnings, but saving is done separately in the call flow.
    """
    entry_price = to_decimal(position.get("entry_price"))
    remaining_qty = to_int(position.get("remaining_qty"))
    ticker_code = position.get("ticker_code")

    current_price = extract_current_price(quote_result)

    if current_price <= 0 and connector_snapshot:
        current_price = to_decimal(connector_snapshot.get("current_price"))

    previous_close = extract_previous_close(quote_result)

    if previous_close <= 0 and connector_snapshot:
        # The snapshot has no previous close, so there is no fallback
        previous_close = Decimal("0")

    sellable_qty = 0
    snapshot_qty = 0
    snapshot_current_price = Decimal("0")

    if connector_snapshot:
        sellable_qty = to_int(connector_snapshot.get("sellable_quantity"))
        snapshot_qty = to_int(connector_snapshot.get("quantity"))
        snapshot_current_price = to_decimal(connector_snapshot.get("current_price"))

    pnl_rate = calculate_rate(current_price, entry_price)
    intraday_drop_rate = calculate_rate(current_price, previous_close)

    should_stop = False
    stop_reason = None

    if pnl_rate is not None and pnl_rate <= hard_stop_rate:
        should_stop = True
        stop_reason = "INTRADAY_ENTRY_HARD_STOP"

    if (
        not should_stop
        and intraday_drop_rate is not None
        and intraday_drop_rate <= hard_stop_rate
    ):
        should_stop = True
        stop_reason = "INTRADAY_PREV_CLOSE_HARD_STOP"

    warnings = []

    if current_price <= 0:
        warnings.append("현재가를 찾지 못함")

    if sellable_qty <= 0:
        warnings.append("매도가능수량이 0 이하")

    if snapshot_qty <= 0:
        warnings.append("connector_position_snapshot 보유수량이 0 이하")

    if remaining_qty <= 0:
        warnings.append("strategy_position_state remaining_qty가 0 이하")

    return {
        "source": SOURCE,
        "position_state_id": position.get("position_state_id"),
        "account_id": position.get("account_id"),
        "account_no": position.get("account_no"),
        "environment": position.get("environment"),
        "ticker_code": ticker_code,
        "stock_name": position.get("stock_name"),
        "entry_date": str(position.get("entry_date")) if position.get("entry_date") is not None else None,
        "entry_price": str(entry_price),
        "remaining_qty": remaining_qty,
        "snapshot_qty": snapshot_qty,
        "sellable_qty": sellable_qty,
        "current_price": str(current_price),
        "snapshot_current_price": str(snapshot_current_price),
        "previous_close": str(previous_close),
        "pnl_rate": str(pnl_rate) if pnl_rate is not None else None,
        "intraday_drop_rate": str(intraday_drop_rate) if intraday_drop_rate is not None else None,
        "hard_stop_rate": str(hard_stop_rate),
        "should_stop": should_stop,
        "stop_reason": stop_reason,
        "warnings": warnings,
        "quote_result": quote_result,
    }


def print_monitor_result(result, index):
    print()
    print(
        f"{index}. position_state_id={result['position_state_id']} "
        f"ticker={result['ticker_code']} "
        f"name={result['stock_name']} "
        f"entry_price={result['entry_price']} "
        f"current_price={result['current_price']} "
        f"remaining_qty={result['remaining_qty']} "
        f"sellable_qty={result['sellable_qty']} "
        f"pnl_rate={result['pnl_rate']} "
        f"intraday_drop_rate={result['intraday_drop_rate']} "
        f"should_stop={result['should_stop']} "
        f"stop_reason={result['stop_reason']}"
    )

    warnings = result.get("warnings") or []
    if warnings:
        print("   WARNINGS")
        for warning in warnings:
            print(f"   - {warning}")

def should_save_intraday_check(monitor_result, created_execution_order_id=None):
    """
    Determine whether to save the Intraday Monitor result.

    Based on the operational UI:
    - If the intraday position check button was executed, save even a normal result.
    - This ensures the "Latest Intraday Position Check Result" on the Daily Batch screen
      is updated with the actual last check result.

    Save targets:
    - Normal check
    - Warning present
    - Stop-loss candidate
    - Order created
    - Current-price lookup failed
    """

    return True

def build_intraday_stop_order_data(position, connector_snapshot, monitor_result, latest_plan):
    """
    Convert the Intraday hard stop result into strategy_execution_order row data.
    """

    current_price = to_decimal(monitor_result.get("current_price"))
    entry_price = to_decimal(monitor_result.get("entry_price"))
    remaining_qty = to_int(monitor_result.get("remaining_qty"))
    sellable_qty = to_int(monitor_result.get("sellable_qty"))

    order_qty = min(remaining_qty, sellable_qty)

    expected_pnl_amount = Decimal("0")
    if current_price > 0 and entry_price > 0 and order_qty > 0:
        expected_pnl_amount = (current_price - entry_price) * Decimal(order_qty)

    expected_pnl_rate = None
    if entry_price > 0:
        expected_pnl_rate = quantize_rate((current_price - entry_price) / entry_price)

    current_eval_amount = Decimal("0")
    if current_price > 0 and remaining_qty > 0:
        current_eval_amount = current_price * Decimal(remaining_qty)

    signal_reason = {
        "source": SOURCE,
        "action": "SELL",
        "reason": monitor_result.get("stop_reason"),
        "detail": "장중 손절 조건 충족",
        "ticker_code": monitor_result.get("ticker_code"),
        "stock_name": monitor_result.get("stock_name"),
        "position_state_id": monitor_result.get("position_state_id"),
        "entry_price": monitor_result.get("entry_price"),
        "current_price": monitor_result.get("current_price"),
        "pnl_rate": monitor_result.get("pnl_rate"),
        "intraday_drop_rate": monitor_result.get("intraday_drop_rate"),
        "hard_stop_rate": monitor_result.get("hard_stop_rate"),
    }

    validation_result = {
        "source": SOURCE,
        "decision_type": "SELL",
        "decision_status": "READY",
        "sell_reason": monitor_result.get("stop_reason"),
        "ticker_code": monitor_result.get("ticker_code"),
        "stock_name": monitor_result.get("stock_name"),
        "position_state_id": monitor_result.get("position_state_id"),
        "remaining_qty": remaining_qty,
        "sellable_qty": sellable_qty,
        "order_qty": order_qty,
        "entry_price": monitor_result.get("entry_price"),
        "current_price": monitor_result.get("current_price"),
        "expected_pnl_amount": str(expected_pnl_amount),
        "expected_pnl_rate": str(expected_pnl_rate) if expected_pnl_rate is not None else None,
        "warnings": monitor_result.get("warnings") or [],
    }

    request_payload = {
        "source": SOURCE,
        "request_type": "INTRADAY_STOP_SELL",
        "execution_plan_id": latest_plan.get("id"),
        "position_state_id": monitor_result.get("position_state_id"),
        "account_no": monitor_result.get("account_no"),
        "ticker_code": monitor_result.get("ticker_code"),
        "stock_name": monitor_result.get("stock_name"),
        "order_qty": order_qty,
        "order_method": "MARKET",
        "create_order_policy": "CREATE_READY_ONLY",
        "auto_submit": False,
    }

    sell_info = {
        "source": SOURCE,
        "action": "SELL",
        "reason": monitor_result.get("stop_reason"),
        "detail": "장중 손절 조건 충족으로 INTRADAY_STOP_SELL 후보 생성",
        "version": "intraday_position_monitor_v1",
        "ticker_code": monitor_result.get("ticker_code"),
        "stock_name": monitor_result.get("stock_name"),
        "position_state_id": monitor_result.get("position_state_id"),
        "entry_date": monitor_result.get("entry_date"),
        "entry_price": monitor_result.get("entry_price"),
        "current_price": monitor_result.get("current_price"),
        "remaining_qty": remaining_qty,
        "sellable_qty": sellable_qty,
        "order_qty": order_qty,
        "pnl_rate": monitor_result.get("pnl_rate"),
        "intraday_drop_rate": monitor_result.get("intraday_drop_rate"),
        "hard_stop_rate": monitor_result.get("hard_stop_rate"),
        "warnings": monitor_result.get("warnings") or [],
    }

    return {
        "execution_plan_id": latest_plan["id"],

        "source_position_state_id": monitor_result.get("position_state_id"),
        "source_daily_run_id": position.get("source_daily_run_id"),
        "source_type": "INTRADAY_STOP_SELL",
        "execution_mode": "PAPER_STRATEGY",

        "account_id": monitor_result.get("account_id"),
        "account_no": monitor_result.get("account_no"),
        "signal_date": latest_plan.get("plan_date"),
        "ticker_code": monitor_result.get("ticker_code"),
        "stock_name": monitor_result.get("stock_name"),

        "action_type": "SELL",
        "signal_type": "SELL",

        "market_signal": latest_plan.get("market_signal"),

        "target_amount": current_eval_amount,
        "current_qty": remaining_qty,
        "current_eval_amount": current_eval_amount,

        "order_qty": order_qty,
        "order_price": Decimal("0"),
        "order_method": "MARKET",

        "execution_status": "READY" if order_qty > 0 else "BLOCKED",
        "block_reason": None if order_qty > 0 else "NO_SELLABLE_QTY",
        "approval_required": False,

        "signal_reason": dumps_json(signal_reason),
        "validation_result": dumps_json(validation_result),
        "request_payload": dumps_json(request_payload),

        "sell_reason": monitor_result.get("stop_reason"),
        "sell_info": dumps_json(sell_info),
        "expected_sell_price": current_price,
        "expected_pnl_amount": expected_pnl_amount,
        "expected_pnl_rate": expected_pnl_rate,
    }


def create_intraday_stop_orders(conn, positions, stop_candidates):
    """
    Create INTRADAY_STOP_SELL READY orders for the stop_candidates.
    Writes to strategy_execution_order and strategy_intraday_position_check occur.
    """

    if not stop_candidates:
        return []

    latest_plan = get_latest_daily_execution_plan(
        conn,
        account_id=stop_candidates[0]["account_id"],
    )

    position_map = {
        p["position_state_id"]: p
        for p in positions
    }

    created_orders = []

    for candidate in stop_candidates:
        position = position_map.get(candidate["position_state_id"])
        if not position:
            print(
                f"[WARN] position_state_id={candidate['position_state_id']} 원본 position을 찾지 못함"
            )
            continue

        connector_snapshot = get_latest_connector_position_snapshot(
            conn,
            account_id=candidate["account_id"],
            ticker_code=candidate["ticker_code"],
        )

        order_data = build_intraday_stop_order_data(
            position=position,
            connector_snapshot=connector_snapshot,
            monitor_result=candidate,
            latest_plan=latest_plan,
        )

        created = upsert_intraday_stop_sell_execution_order(
            conn,
            order_data,
        )

        created_orders.append(created)

        if should_save_intraday_check(
            monitor_result=candidate,
            created_execution_order_id=created["id"],
        ):
            saved = insert_intraday_position_check(
                conn=conn,
                monitor_result=candidate,
                created_execution_order_id=created["id"],
            )

            print(
                f"[SAVED] intraday_check_id={saved['id']} "
                f"execution_order_id={created['id']} "
                f"ticker={candidate['ticker_code']} "
                f"reason={candidate['stop_reason']}"
            )

    return created_orders

def main():
    args = parse_args()
    hard_stop_rate = to_decimal(args.hard_stop_rate, "-0.10")

    conn = get_conn()
    conn.autocommit = False

    try:
        account = get_account(conn)

        positions = get_open_strategy_positions_for_intraday_monitor(
            conn,
            account_id=account["id"],
        )

        if args.limit and len(positions) > args.limit:
            positions = positions[:args.limit]

        print_header("[Intraday Position Monitor]")
        print(f"account_no      : {account['account_no']}")
        print(f"environment     : {account['environment']}")
        print(f"hard_stop_rate  : {hard_stop_rate}")
        print(f"open_positions  : {len(positions)}")

        if not positions:
            print()
            print(t("[WARN] No OPEN position to monitor intraday", "[WARN] 장중 모니터링 대상 OPEN 포지션 없음"))
            conn.rollback()
            return

        stop_candidates = []

        for idx, position in enumerate(positions, start=1):
            ticker_code = position["ticker_code"]

            connector_snapshot = get_latest_connector_position_snapshot(
                conn,
                account_id=position["account_id"],
                ticker_code=ticker_code,
            )

            quote_result = get_stock_price(
                stock_code=ticker_code,
                save_db=True,
            )

            result = build_monitor_result(
                position=position,
                connector_snapshot=connector_snapshot,
                quote_result=quote_result,
                hard_stop_rate=hard_stop_rate,
            )

            print_monitor_result(result, idx)

            if should_save_intraday_check(result):
                saved = insert_intraday_position_check(
                    conn=conn,
                    monitor_result=result,
                )

                print(
                    f"   [SAVED] intraday_check_id={saved['id']} "
                    f"should_stop={saved['should_stop']} "
                    f"warning_count={saved['warning_count']}"
                )

            if result["should_stop"]:
                stop_candidates.append(result)

        print_header("[Intraday Monitor Summary]")
        print(f"checked_positions : {len(positions)}")
        print(f"stop_candidates   : {len(stop_candidates)}")

        if not stop_candidates:
            print()
            print(t("[NO_TARGET] No position meeting the intraday stop-loss condition", "[NO_TARGET] 장중 손절 조건 충족 포지션 없음"))
            conn.commit()
            return

        print()
        print(t("[ALERT] Intraday stop-loss candidate detected", "[ALERT] 장중 손절 후보 발생"))
        for candidate in stop_candidates:
            print(
                f"- position_state_id={candidate['position_state_id']} "
                f"ticker={candidate['ticker_code']} "
                f"name={candidate['stock_name']} "
                f"pnl_rate={candidate['pnl_rate']} "
                f"reason={candidate['stop_reason']}"
            )

        if not args.create_order:
            print()
            print(t("Query/validation only complete. --create-order is required to create the INTRADAY_STOP_SELL READY order.", "조회/검증만 완료. INTRADAY_STOP_SELL READY 주문 생성은 --create-order 필요."))
            print(t("Check results were already stored in the position loop.", "점검 결과는 position loop에서 이미 저장됨."))

            conn.commit()
            return

        print_header("[Create INTRADAY_STOP_SELL Orders]")

        created_orders = create_intraday_stop_orders(
            conn=conn,
            positions=positions,
            stop_candidates=stop_candidates,
        )

        conn.commit()

        print(f"created_order_count : {len(created_orders)}")

        for order in created_orders:
            print(
                f"- execution_order_id={order['id']} "
                f"plan_id={order['execution_plan_id']} "
                f"source_type={order['source_type']} "
                f"action={order['action_type']} "
                f"status={order['execution_status']} "
                f"ticker={order['ticker_code']} "
                f"name={order['stock_name']} "
                f"qty={order['order_qty']} "
                f"reason={order['sell_reason']}"
            )

    except Exception as e:
        conn.rollback()
        print_header("[ERROR]")
        print(str(e))
        raise

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
