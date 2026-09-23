# C:\Workspaces\port_strategy_execution\execution_daily_signal_builder.py

"""
Builder that converts a Daily BUY signal into strategy_execution_order storage data.
It queries the account/balance, existing position, latest price, and open orders to build BUY order candidates and a validation payload.
Quantity sizing uses the execution_buy_sizing policy.
"""

from decimal import Decimal

from execution_config import MIN_ORDER_AMOUNT
from execution_buy_sizing import calculate_buy_order_sizing
from execution_repository import (
    get_current_position,
    get_latest_price,
    has_open_connector_order,
    dumps_json,
)


MAX_ORDER_AMOUNT_RATIO = Decimal("0.50")
MAX_ORDER_AMOUNT_POLICY = "TOTAL_EVAL_AMOUNT_50_PERCENT"


def to_decimal(value, default="0"):
    if value is None:
        return Decimal(default)

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    if isinstance(value, str):
        if value.strip() == "":
            return Decimal(default)
        return Decimal(value)

    return Decimal(default)


def to_int(value, default=0):
    if value is None:
        return default

    try:
        return int(value)
    except Exception:
        return default


def normalize_info(value):
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    return {}


def get_balance_value(balance, key, default="0"):
    if not balance:
        return Decimal(default)

    return to_decimal(balance.get(key), default)


def calculate_max_order_amount(total_eval_amount):
    """
    Compute the maximum order amount per stock.

    Current policy:
    - Use 50% of the total evaluation amount as the single-order cap
    - Can later be migrated to execution_config.DEFAULT_MAX_ORDER_AMOUNT_RATIO
    """

    total_eval_amount = to_decimal(total_eval_amount, "0")

    if total_eval_amount <= 0:
        return None

    return total_eval_amount * MAX_ORDER_AMOUNT_RATIO


def build_daily_signal_validation(
    *,
    ticker_code,
    market_signal,
    available_cash,
    latest_price,
    account_id,
    conn,
):
    reasons = []

    if not ticker_code:
        reasons.append("ticker_code is null")

    if market_signal == "BLOCK":
        reasons.append("market_signal=BLOCK")

    if available_cash <= 0:
        reasons.append("available_cash <= 0")

    if latest_price is None or latest_price <= 0:
        reasons.append("latest_price is null or <= 0")

    if ticker_code and has_open_connector_order(conn, account_id, ticker_code):
        reasons.append("open connector order exists")

    return reasons


def build_daily_signal_buy_execution_order(
    conn,
    plan_id,
    account,
    balance,
    daily_run,
    signal,
    available_cash_override=None,
    allocation_sequence=None,
    initial_available_cash=None,
):
    """
    Convert a strategy_daily_signal row into a BUY execution candidate.

    Key points:
    - The BUY judgment / position_size is already decided in the Daily Signal
    - Here it is converted into an order quantity based on the actual account
    - Quantity calculation is delegated to execution_buy_sizing.calculate_buy_order_sizing()
    """

    account_id = account["id"]
    account_no = account["account_no"]

    buy_info = normalize_info(signal.get("buy_info"))
    raw_features = normalize_info(signal.get("raw_features"))

    ticker_code = signal.get("ticker_code")
    stock_name = signal.get("company_name")

    market_signal = (
        signal.get("market_signal")
        or daily_run.get("market_signal")
        or buy_info.get("entry_market_signal")
    )

    position_size = to_decimal(signal.get("position_size"), "0")
    final_score = to_decimal(signal.get("final_score"), "0")
    flow_score = to_decimal(signal.get("flow_score"), "0")
    info_score = to_decimal(signal.get("info_score"), "0")
    tape_score = to_decimal(signal.get("tape_score"), "0")
    short_pressure_score = to_decimal(signal.get("short_score"), "0")

    balance_available_cash = (
        get_balance_value(balance, "orderable_cash", "0")
        or get_balance_value(balance, "cash_balance", "0")
        or Decimal("0")
    )

    if available_cash_override is None:
        available_cash = balance_available_cash
    else:
        available_cash = max(
            to_decimal(available_cash_override, "0"),
            Decimal("0"),
        )

    if initial_available_cash is None:
        allocation_initial_cash = balance_available_cash
    else:
        allocation_initial_cash = max(
            to_decimal(initial_available_cash, "0"),
            Decimal("0"),
        )

    total_eval_amount = (
        get_balance_value(balance, "total_eval_amount", "0")
        or available_cash
    )

    max_order_amount = calculate_max_order_amount(total_eval_amount)

    position = get_current_position(conn, account_id, ticker_code)
    latest_price = get_latest_price(conn, ticker_code)

    current_qty = to_int(position.get("quantity"), 0)
    current_eval_amount = to_decimal(position.get("eval_amount"), "0")

    position_snapshot_detail = {
        "source": "connector_position_snapshot",
        "quantity_key": "quantity",
        "eval_amount_key": "eval_amount",
        "current_qty": current_qty,
        "current_eval_amount": str(current_eval_amount),
    }

    # -------------------------------------------------
    # 1. Common execution-candidate validation
    # -------------------------------------------------
    validation_reasons = build_daily_signal_validation(
        ticker_code=ticker_code,
        market_signal=market_signal,
        available_cash=available_cash,
        latest_price=latest_price,
        account_id=account_id,
        conn=conn,
    )

    if position_size <= 0:
        validation_reasons.append("BUY but position_size <= 0")

    # -------------------------------------------------
    # 2. Compute the BUY order quantity
    # -------------------------------------------------
    sizing_result = calculate_buy_order_sizing(
        available_cash=available_cash,
        total_eval_amount=total_eval_amount,
        position_size=position_size,
        latest_price=latest_price,
        current_position_qty=current_qty,
        current_position_eval_amount=current_eval_amount,
        min_order_amount=MIN_ORDER_AMOUNT,
        max_order_amount=max_order_amount,
    )

    sizing_validation_reasons = sizing_result.get("validation_reasons") or []

    for reason in sizing_validation_reasons:
        if reason not in validation_reasons:
            validation_reasons.append(reason)

    target_amount = sizing_result["target_amount"]
    order_qty = sizing_result["order_qty"]
    order_price = latest_price
    estimated_order_amount = sizing_result["estimated_order_amount"]
    required_cash_amount = sizing_result["required_cash_amount"]
    market_buy_cash_reserve_ratio = sizing_result[
        "market_buy_cash_reserve_ratio"
    ]
    market_buy_cash_reserve_policy = sizing_result[
        "market_buy_cash_reserve_policy"
    ]
    sizing_detail = sizing_result["sizing_detail"]

    # -------------------------------------------------
    # 3. Determine the Execution status
    # -------------------------------------------------
    if validation_reasons:
        execution_status = "BLOCKED"
        block_reason = " / ".join(validation_reasons)
    else:
        execution_status = "READY"
        block_reason = None

    # -------------------------------------------------
    # 4. Store validation_result
    # -------------------------------------------------
    reserved_amount = (
        min(required_cash_amount, available_cash)
        if execution_status == "READY"
        else Decimal("0")
    )
    available_cash_after_order = max(
        available_cash - reserved_amount,
        Decimal("0"),
    )

    validation_result = {
        "validation_reasons": validation_reasons,

        "cash_allocation": {
            "allocation_policy": "SEQUENTIAL_READY_ORDER_RESERVATION_V1",
            "allocation_sequence": allocation_sequence,
            "initial_available_cash": str(allocation_initial_cash),
            "available_cash_before_order": str(available_cash),
            "reserved_amount": str(reserved_amount),
            "available_cash_after_order": str(
                available_cash_after_order
            ),
            "reserve_basis": "required_cash_amount",
            "estimated_order_amount": str(estimated_order_amount),
            "required_cash_amount": str(required_cash_amount),
            "market_buy_cash_reserve_ratio": str(
                market_buy_cash_reserve_ratio
            ),
            "market_buy_cash_reserve_policy": (
                market_buy_cash_reserve_policy
            ),
        },

        # New structure: separated for cleaner structural display on the View / operational screen
        "sizing": {
            "method": sizing_detail.get("sizing_method"),
            "detail": sizing_detail,
        },

        "account_snapshot": {
            "account_id": account_id,
            "account_no": account_no,
            "available_cash": str(available_cash),
            "total_eval_amount": str(total_eval_amount),
            "max_order_amount": str(max_order_amount) if max_order_amount is not None else None,
            "max_order_amount_policy": MAX_ORDER_AMOUNT_POLICY,
            "max_order_amount_ratio": str(MAX_ORDER_AMOUNT_RATIO),
            "min_order_amount": str(MIN_ORDER_AMOUNT),
        },

        "position_snapshot": {
            "source": "connector_position_snapshot",
            "quantity_key": "quantity",
            "eval_amount_key": "eval_amount",
            "current_qty": current_qty,
            "current_eval_amount": str(current_eval_amount),
        },

        "order_snapshot": {
            "latest_price": str(latest_price) if latest_price is not None else None,
            "target_amount": str(target_amount),
            "estimated_order_amount": str(estimated_order_amount),
            "required_cash_amount": str(required_cash_amount),
            "market_buy_cash_reserve_ratio": str(
                market_buy_cash_reserve_ratio
            ),
            "order_qty": order_qty,
            "order_price": str(order_price) if order_price is not None else None,
            "order_method": "MARKET",
        },

        "rebalance_formula": (
            "additional_buy_amount = "
            "total_eval_amount * position_size - current_position_eval_amount"
        ),

        "source": {
            "source_table": "strategy_daily_signal",
            "daily_run_id": signal.get("daily_run_id"),
            "daily_signal_id": signal.get("id"),
            "data_date": str(signal.get("data_date")),
            "signal_date": str(signal.get("signal_date")),
            "rank_no": signal.get("rank_no"),
        },

        # Flat fields for backward compatibility / SQL query convenience
        "available_cash": str(available_cash),
        "total_eval_amount": str(total_eval_amount),
        "max_order_amount": str(max_order_amount) if max_order_amount is not None else None,
        "max_order_amount_policy": MAX_ORDER_AMOUNT_POLICY,
        "latest_price": str(latest_price) if latest_price is not None else None,

        "current_qty": current_qty,
        "current_eval_amount": str(current_eval_amount),
        "position_snapshot_detail": position_snapshot_detail,

        "target_amount": str(target_amount),
        "estimated_order_amount": str(estimated_order_amount),
        "required_cash_amount": str(required_cash_amount),
        "market_buy_cash_reserve_ratio": str(
            market_buy_cash_reserve_ratio
        ),
        "market_buy_cash_reserve_policy": (
            market_buy_cash_reserve_policy
        ),
        "order_qty": order_qty,

        "sizing_detail": sizing_detail,
    }

    signal_reason = {
        "entry_reason": signal.get("entry_reason"),
        "block_reason": signal.get("block_reason"),
        "buy_info": buy_info,
        "raw_features": raw_features,
        "source_table": signal.get("source_table"),
        "processor_version": signal.get("processor_version"),
    }

    return {
        "execution_plan_id": plan_id,

        "source_daily_run_id": signal["daily_run_id"],
        "source_daily_signal_id": signal["id"],
        "source_type": "DAILY_SIGNAL_BUY",
        "execution_mode": "DRY_RUN",

        "account_id": account_id,
        "account_no": account_no,

        "signal_date": signal["signal_date"],
        "ticker_code": ticker_code,
        "stock_name": stock_name,

        "action_type": "BUY",
        "signal_type": "BUY",
        "signal_score": final_score,
        "signal_position_size": position_size,

        "market_signal": market_signal,
        "market_regime_score": None,
        "flow_score": flow_score,
        "info_score": info_score,
        "tape_score": tape_score,
        "final_score": final_score,
        "short_pressure_score": short_pressure_score,

        "target_weight": position_size,
        "target_amount": target_amount,
        "current_qty": current_qty,
        "current_eval_amount": current_eval_amount,

        "order_qty": order_qty,
        "order_price": order_price,
        "order_method": "MARKET",

        # Internal values for sequential cash reservation across multiple BUY candidates.
        # These are not Repository storage columns; the caller computes the next candidate's balance.
        "estimated_order_amount": estimated_order_amount,
        "required_cash_amount": required_cash_amount,

        "execution_status": execution_status,
        "block_reason": block_reason,

        "signal_reason": dumps_json(signal_reason),
        "validation_result": dumps_json(validation_result),
    }


def build_daily_signal_execution_orders(
    conn,
    plan_id,
    account,
    balance,
    daily_run,
    signals,
):
    """
    Generate Daily BUY candidates in input order, sequentially reserving READY order amounts.

    Policy:
    - Use the initial orderable_cash as the common budget for all candidates
    - Deduct the READY order's required_cash_amount (110% of the estimated order amount) from the next candidate's budget
    - BLOCKED orders do not reserve cash
    - The remaining cash never goes below 0
    """

    order_data_list = []

    initial_available_cash = (
        get_balance_value(balance, "orderable_cash", "0")
        or get_balance_value(balance, "cash_balance", "0")
        or Decimal("0")
    )
    remaining_cash = max(
        initial_available_cash,
        Decimal("0"),
    )

    for allocation_sequence, signal in enumerate(
        signals,
        start=1,
    ):
        order_data = build_daily_signal_buy_execution_order(
            conn=conn,
            plan_id=plan_id,
            account=account,
            balance=balance,
            daily_run=daily_run,
            signal=signal,
            available_cash_override=remaining_cash,
            allocation_sequence=allocation_sequence,
            initial_available_cash=initial_available_cash,
        )

        if order_data.get("execution_status") == "READY":
            reserved_amount = min(
                to_decimal(
                    order_data.get(
                        "required_cash_amount"
                    ),
                    "0",
                ),
                remaining_cash,
            )
            remaining_cash = max(
                remaining_cash - reserved_amount,
                Decimal("0"),
            )

        order_data_list.append(order_data)

    return order_data_list
