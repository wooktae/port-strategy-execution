"""
Loader that combines OPEN strategy_position_state with the connector position snapshot.
It builds the context used by position evaluation and the SELL builder, and performs DB queries.
There is an executable main at the bottom of the file, so confirm whether it is merely an import target before handling it.
"""

from datetime import date
from decimal import Decimal

from execution_db import fetch_all


ACTIVE_POSITION_STATUSES = ("OPEN", "SELL_READY", "SELL_ORDERED")


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


def to_date(value):
    if value is None:
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def calc_return_rate(current_price, entry_price):
    current_price = to_decimal(current_price)
    entry_price = to_decimal(entry_price)

    if entry_price <= 0:
        return Decimal("0")

    return (current_price / entry_price) - Decimal("1")


def calc_pnl_amount(current_price, entry_price, qty):
    current_price = to_decimal(current_price)
    entry_price = to_decimal(entry_price)
    qty = to_int(qty)

    return (current_price - entry_price) * Decimal(qty)


def calc_holding_days(plan_date, entry_date):
    plan_date = to_date(plan_date)
    entry_date = to_date(entry_date)

    if not plan_date or not entry_date:
        return 0

    return max(0, (plan_date - entry_date).days)


def get_open_strategy_positions(conn, account_id):
    """
    Query OPEN / SELL_READY / SELL_ORDERED positions from the strategy perspective.

    Note:
    - This does not join directly with the actual holdings snapshot here.
    - It fetches only the pure strategy position state.
    - Actual holding status is validated separately in get_latest_position_snapshot().
    """

    sql = """
        SELECT
            id,
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
            last_evaluated_date,
            latest_sell_reason,
            latest_sell_info,
            latest_validation_result,
            buy_info,
            memo,
            created_at,
            updated_at
        FROM strategy_position_state
        WHERE account_id = %(account_id)s
          AND position_status IN ('OPEN', 'SELL_READY', 'SELL_ORDERED')
        ORDER BY entry_date ASC, id ASC
    """

    return fetch_all(conn, sql, {"account_id": account_id})


def get_latest_position_snapshot(conn, account_id, ticker_code):
    """
    Query the latest connector_position_snapshot by account + stock.
    """

    sql = """
        SELECT
            account_id,
            account_no,
            ticker_code,
            stock_name,
            market,
            as_of_date,
            as_of_ts,
            quantity,
            sellable_quantity,
            avg_buy_price,
            buy_amount,
            current_price,
            eval_amount,
            eval_profit,
            eval_profit_rate,
            raw_json,
            source_api,
            source_version,
            created_at
        FROM connector_position_snapshot
        WHERE account_id = %(account_id)s
          AND ticker_code = %(ticker_code)s
        ORDER BY as_of_date DESC, as_of_ts DESC
        LIMIT 1
    """

    rows = fetch_all(conn, sql, {
        "account_id": account_id,
        "ticker_code": ticker_code,
    })

    return rows[0] if rows else None


def build_position_context(position_state, snapshot, plan_date):
    """
    Combine strategy_position_state + connector_position_snapshot
    to build the context for operational SELL Logic evaluation.
    """

    entry_price = to_decimal(position_state.get("entry_price"))
    remaining_qty = to_int(position_state.get("remaining_qty"))

    snapshot_qty = 0
    sellable_qty = 0
    avg_buy_price = None
    current_price = None
    eval_profit = None
    eval_profit_rate = None
    snapshot_date = None
    snapshot_ts = None

    has_snapshot = snapshot is not None

    if snapshot:
        snapshot_qty = to_int(snapshot.get("quantity"))
        sellable_qty = to_int(snapshot.get("sellable_quantity"))
        avg_buy_price = to_decimal(snapshot.get("avg_buy_price"))
        current_price = to_decimal(snapshot.get("current_price"))
        eval_profit = to_decimal(snapshot.get("eval_profit"))
        eval_profit_rate = to_decimal(snapshot.get("eval_profit_rate"))
        snapshot_date = snapshot.get("as_of_date")
        snapshot_ts = snapshot.get("as_of_ts")

    # For operational SELL judgment, use the current price if available,
    # otherwise use entry_price as a fallback.
    effective_current_price = (
        current_price if current_price and current_price > 0 else entry_price
    )

    expected_pnl_rate = calc_return_rate(effective_current_price, entry_price)
    expected_pnl_amount = calc_pnl_amount(
        effective_current_price,
        entry_price,
        remaining_qty,
    )
    holding_days = calc_holding_days(plan_date, position_state.get("entry_date"))

    validation_warnings = []

    if not has_snapshot:
        validation_warnings.append("NO_CONNECTOR_POSITION_SNAPSHOT")

    if snapshot_qty <= 0:
        validation_warnings.append("SNAPSHOT_QTY_ZERO_OR_MISSING")

    if remaining_qty <= 0:
        validation_warnings.append("REMAINING_QTY_ZERO_OR_MISSING")

    if sellable_qty <= 0:
        validation_warnings.append("SELLABLE_QTY_ZERO_OR_MISSING")

    if effective_current_price <= 0:
        validation_warnings.append("CURRENT_PRICE_ZERO_OR_MISSING")

    return {
        "position_state_id": position_state.get("id"),
        "account_id": position_state.get("account_id"),
        "account_no": position_state.get("account_no"),
        "ticker_code": position_state.get("ticker_code"),
        "stock_name": position_state.get("stock_name"),

        "source_buy_execution_order_id": position_state.get("source_buy_execution_order_id"),
        "source_connector_order_request_id": position_state.get("source_connector_order_request_id"),
        "source_connector_fill_id": position_state.get("source_connector_fill_id"),

        "entry_date": position_state.get("entry_date"),
        "entry_price": entry_price,
        "entry_qty": to_int(position_state.get("entry_qty")),
        "remaining_qty": remaining_qty,
        "position_status": position_state.get("position_status"),

        "snapshot_qty": snapshot_qty,
        "sellable_qty": sellable_qty,
        "avg_buy_price": avg_buy_price,
        "current_price": effective_current_price,
        "raw_current_price": current_price,
        "eval_profit": eval_profit,
        "eval_profit_rate": eval_profit_rate,
        "snapshot_date": snapshot_date,
        "snapshot_ts": snapshot_ts,

        "holding_days": holding_days,
        "expected_pnl_rate": expected_pnl_rate,
        "expected_pnl_amount": expected_pnl_amount,

        "buy_info": position_state.get("buy_info") or {},
        "latest_sell_info": position_state.get("latest_sell_info"),
        "last_evaluated_date": position_state.get("last_evaluated_date"),

        "validation_warnings": validation_warnings,
    }


def load_position_contexts(conn, account_id, plan_date):
    """
    Build the list of position contexts targeted by operational SELL Logic.
    """

    position_states = get_open_strategy_positions(conn, account_id)

    contexts = []

    for ps in position_states:
        snapshot = get_latest_position_snapshot(
            conn=conn,
            account_id=account_id,
            ticker_code=ps.get("ticker_code"),
        )

        ctx = build_position_context(
            position_state=ps,
            snapshot=snapshot,
            plan_date=plan_date,
        )

        contexts.append(ctx)

    return contexts


# ---------------------------------------------------------
# Standalone test entrypoint
# ---------------------------------------------------------
from execution_db import get_conn
from execution_repository import get_account
from execution_position_loader import load_position_contexts


def main():
    conn = get_conn()

    try:
        account = get_account(conn)

        # Test reference date.
        # If needed, this can later be improved to pass backtest_execution_run's plan_date.
        plan_date = "2026-04-30"

        contexts = load_position_contexts(
            conn=conn,
            account_id=account["id"],
            plan_date=plan_date,
        )

        print()
        print("========================================")
        print("[Position Context Loader Test]")
        print("========================================")
        print(f"account_id : {account['id']}")
        print(f"account_no : {account['account_no']}")
        print(f"plan_date  : {plan_date}")
        print(f"contexts   : {len(contexts)}")

        for ctx in contexts:
            print()
            print("----------------------------------------")
            print(f"position_state_id : {ctx['position_state_id']}")
            print(f"ticker            : {ctx['ticker_code']} / {ctx['stock_name']}")
            print(f"status            : {ctx['position_status']}")
            print(f"entry_date        : {ctx['entry_date']}")
            print(f"entry_price       : {ctx['entry_price']}")
            print(f"remaining_qty     : {ctx['remaining_qty']}")
            print(f"snapshot_qty      : {ctx['snapshot_qty']}")
            print(f"sellable_qty      : {ctx['sellable_qty']}")
            print(f"current_price     : {ctx['current_price']}")
            print(f"holding_days      : {ctx['holding_days']}")
            print(f"expected_pnl_rate : {ctx['expected_pnl_rate']}")
            print(f"expected_pnl_amt  : {ctx['expected_pnl_amount']}")
            print(f"warnings          : {ctx['validation_warnings']}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
