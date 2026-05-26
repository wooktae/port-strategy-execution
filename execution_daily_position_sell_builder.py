# C:\Workspaces\port_strategy_execution\execution_daily_position_sell_builder.py

from decimal import Decimal

from execution_repository import dumps_json


DEFAULT_EXECUTION_MODE = "REVIEW"
DEFAULT_ORDER_METHOD = "MARKET"


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


def normalize_json(value):
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    return {}


def build_daily_position_sell_order_data(
    *,
    plan_id,
    account,
    daily_run,
    decision,
):
    """
    strategy_daily_position_decision SELL READY row를
    strategy_execution_order insert용 dict로 변환.
    """

    sell_info = normalize_json(decision.get("sell_info"))
    validation_result = normalize_json(decision.get("validation_result"))
    position_context = normalize_json(decision.get("position_context"))

    order_qty = to_int(decision.get("order_qty"), 0)
    order_price = to_decimal(decision.get("order_price"), "0")

    current_qty = to_int(decision.get("current_qty"), 0)
    current_eval_amount = order_price * Decimal(current_qty)

    signal_score = to_decimal(decision.get("final_score"), "0")
    signal_position_size = Decimal("0")

    signal_reason = {
        "source": "strategy_daily_position_decision",
        "daily_run_id": decision.get("daily_run_id"),
        "daily_position_decision_id": decision.get("id"),
        "position_state_id": decision.get("position_state_id"),
        "decision_type": decision.get("decision_type"),
        "decision_status": decision.get("decision_status"),
        "sell_reason": decision.get("sell_reason"),
        "hold_reason": decision.get("hold_reason"),
        "skip_reason": decision.get("skip_reason"),
        "sell_info": sell_info,
        "position_context": position_context,
        "processor_version": decision.get("processor_version"),
    }

    validation_payload = {
        "source": "execution_daily_position_sell_builder",
        "daily_run_id": decision.get("daily_run_id"),
        "daily_position_decision_id": decision.get("id"),
        "position_state_id": decision.get("position_state_id"),
        "ticker_code": decision.get("ticker_code"),
        "stock_name": decision.get("stock_name"),
        "order_qty": order_qty,
        "order_price": str(order_price),
        "expected_pnl_amount": str(decision.get("expected_pnl_amount")),
        "expected_pnl_rate": str(decision.get("expected_pnl_rate")),
        "decision_validation_result": validation_result,
    }

    execution_status = "READY"
    block_reason = None

    if order_qty <= 0:
        execution_status = "BLOCKED"
        block_reason = "order_qty <= 0"

    if order_price <= 0:
        execution_status = "BLOCKED"
        block_reason = "order_price <= 0" if block_reason is None else block_reason + " / order_price <= 0"

    return {
        "execution_plan_id": plan_id,

        "source_position_state_id": decision["position_state_id"],
        "source_daily_run_id": decision["daily_run_id"],
        "source_daily_position_decision_id": decision["id"],
        "source_type": "DAILY_POSITION_SELL",
        "execution_mode": DEFAULT_EXECUTION_MODE,

        "account_id": account["id"],
        "account_no": account["account_no"],

        "signal_date": decision["decision_date"],
        "ticker_code": decision["ticker_code"],
        "stock_name": decision["stock_name"],

        "action_type": "SELL",
        "signal_type": "SELL",
        "signal_score": signal_score,
        "signal_position_size": signal_position_size,

        "market_signal": decision.get("market_signal"),
        "market_regime_score": decision.get("market_regime_score"),
        "flow_score": decision.get("flow_score"),
        "info_score": decision.get("info_score"),
        "tape_score": decision.get("tape_score"),
        "final_score": decision.get("final_score"),
        "short_pressure_score": decision.get("short_pressure_score"),

        "target_weight": Decimal("0"),
        "target_amount": decision.get("target_amount") or Decimal("0"),
        "current_qty": current_qty,
        "current_eval_amount": current_eval_amount,

        "order_qty": order_qty,
        "order_price": order_price,
        "order_method": DEFAULT_ORDER_METHOD,

        "execution_status": execution_status,
        "block_reason": block_reason,

        "signal_reason": dumps_json(signal_reason),
        "validation_result": dumps_json(validation_payload),

        "sell_reason": decision.get("sell_reason"),
        "sell_info": dumps_json(sell_info),
        "expected_sell_price": order_price,
        "expected_pnl_amount": decision.get("expected_pnl_amount"),
        "expected_pnl_rate": decision.get("expected_pnl_rate"),
    }


def build_daily_position_sell_execution_orders(
    *,
    plan_id,
    account,
    daily_run,
    decisions,
):
    order_data_list = []

    for decision in decisions:
        order_data_list.append(
            build_daily_position_sell_order_data(
                plan_id=plan_id,
                account=account,
                daily_run=daily_run,
                decision=decision,
            )
        )

    return order_data_list