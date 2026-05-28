# C:\Workspaces\port_strategy_execution\execution_builder.py

"""
backtest buy/sell 후보를 strategy_execution_order 저장 데이터로 변환하는 builder.
DB repository helper를 일부 조회 용도로 사용하며 실제 저장은 호출자 entrypoint에서 수행한다.
주문 수량, 금액, validation payload 계산 의미가 바뀌지 않도록 주의한다.
"""

from decimal import Decimal, ROUND_DOWN

from execution_config import MIN_ORDER_AMOUNT
from execution_repository import (
    get_current_position,
    get_latest_price,
    has_open_connector_order,
    dumps_json,
)


def to_decimal(value, default="0"):
    """
    dict/json 값에서 Decimal을 안전하게 추출.
    buy_info/sell_info 값이 None, '', float, int, Decimal 어느 형태여도 처리.
    """

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
    """
    psycopg2 jsonb는 보통 dict로 들어오지만,
    환경에 따라 문자열 JSON처럼 들어올 가능성도 있어 일단 방어.
    지금은 문자열이면 빈 dict로 처리.
    """

    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    return {}


def get_info_value(info, key, default="0"):
    if not info:
        return Decimal(default)

    return to_decimal(info.get(key), default)


def build_common_validation(
    *,
    action_type,
    ticker_code,
    market_signal,
    available_cash,
    latest_price,
    position,
    account_id,
    conn,
):
    reasons = []

    if not ticker_code:
        reasons.append("ticker_code is null")

    if market_signal == "BLOCK" and action_type == "BUY":
        reasons.append("market_signal=BLOCK")

    if available_cash <= 0 and action_type == "BUY":
        reasons.append("available_cash <= 0")

    if latest_price is None or latest_price <= 0:
        reasons.append("latest_price is null or <= 0")

    if ticker_code and has_open_connector_order(conn, account_id, ticker_code):
        reasons.append("open connector order exists")

    if action_type == "SELL":
        current_qty = to_int(position.get("quantity"), 0)
        if current_qty <= 0:
            reasons.append("SELL but current_qty <= 0")

    return reasons


def build_buy_execution_order(conn, plan_id, account, balance, market_daily, trade):
    """
    strategy_trade_log의 buy_date=plan_date row를 BUY execution candidate로 변환.
    """

    account_id = account["id"]
    account_no = account["account_no"]

    buy_info = normalize_info(trade.get("buy_info"))

    ticker_code = trade.get("ticker_code")
    stock_name = trade.get("company_name")

    market_signal = (
        buy_info.get("entry_market_signal")
        or market_daily.get("market_signal")
    )

    position_size = get_info_value(buy_info, "position_size", "0")
    final_score = get_info_value(buy_info, "score", "0")
    flow_score = get_info_value(buy_info, "flow", "0")
    info_score = get_info_value(buy_info, "info", "0")
    tape_score = get_info_value(buy_info, "tape", "0")
    short_pressure_score = get_info_value(buy_info, "short", "0")

    available_cash = balance["orderable_cash"] or balance["cash_balance"] or Decimal("0")

    position = get_current_position(conn, account_id, ticker_code)
    latest_price = get_latest_price(conn, ticker_code)

    validation_reasons = build_common_validation(
        action_type="BUY",
        ticker_code=ticker_code,
        market_signal=market_signal,
        available_cash=available_cash,
        latest_price=latest_price,
        position=position,
        account_id=account_id,
        conn=conn,
    )

    if position_size <= 0:
        validation_reasons.append("BUY but position_size <= 0")

    target_amount = Decimal("0")
    order_qty = 0
    order_price = latest_price

    if latest_price and latest_price > 0:
        target_amount = available_cash * position_size

        if target_amount < MIN_ORDER_AMOUNT:
            validation_reasons.append("target_amount < MIN_ORDER_AMOUNT")

        order_qty = int(
            (target_amount / latest_price).to_integral_value(rounding=ROUND_DOWN)
        )

        if order_qty <= 0:
            validation_reasons.append("order_qty <= 0")

    if validation_reasons:
        execution_status = "BLOCKED"
        block_reason = " / ".join(validation_reasons)
    else:
        execution_status = "READY"
        block_reason = None

    validation_result = {
        "validation_reasons": validation_reasons,
        "available_cash": str(available_cash),
        "latest_price": str(latest_price) if latest_price is not None else None,
        "current_qty": position.get("quantity"),
        "current_eval_amount": str(position.get("eval_amount")),
        "source": "strategy_trade_log.buy_date",
    }

    return {
        "execution_plan_id": plan_id,
        "source_run_id": trade["run_id"],
        "source_trade_log_id": trade["id"],
        "source_type": "TRADE_LOG_BUY",
        "execution_mode": "DRY_RUN",
        "account_id": account_id,
        "account_no": account_no,
        "signal_date": trade["buy_date"],
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
        "current_qty": position.get("quantity"),
        "current_eval_amount": position.get("eval_amount"),
        "order_qty": order_qty,
        "order_price": order_price,
        "order_method": "MARKET",
        "execution_status": execution_status,
        "block_reason": block_reason,
        "signal_reason": dumps_json({
            "buy_info": buy_info,
            "buy_open_price": str(trade.get("buy_open_price")),
            "buy_close_price": str(trade.get("buy_close_price")),
            "buy_low_price": str(trade.get("buy_low_price")),
        }),
        "validation_result": dumps_json(validation_result),
    }


def build_sell_execution_order(conn, plan_id, account, balance, market_daily, trade):
    """
    strategy_trade_log의 sell_date=plan_date row를 SELL execution candidate로 변환.

    중요:
    - SELL은 백테스트상 매도 후보여도 실제 계좌에 보유 수량이 있어야 READY.
    - 실제 보유 수량이 없으면 BLOCKED 처리.
    """

    account_id = account["id"]
    account_no = account["account_no"]

    buy_info = normalize_info(trade.get("buy_info"))
    sell_info = normalize_info(trade.get("sell_info"))

    ticker_code = trade.get("ticker_code")
    stock_name = trade.get("company_name")

    market_signal = (
        sell_info.get("market_signal")
        or buy_info.get("entry_market_signal")
        or market_daily.get("market_signal")
    )

    final_score = get_info_value(sell_info, "final_score", "0")
    flow_score = get_info_value(sell_info, "flow_score", "0")
    info_score = get_info_value(sell_info, "info_score", "0")
    tape_score = get_info_value(sell_info, "tape_score", "0")
    short_pressure_score = get_info_value(sell_info, "short_pressure_score", "0")

    # sell_info에 점수 key가 없을 수 있어서 buy_info 기준으로 fallback
    if final_score == 0:
        final_score = get_info_value(buy_info, "score", "0")
    if flow_score == 0:
        flow_score = get_info_value(buy_info, "flow", "0")
    if info_score == 0:
        info_score = get_info_value(buy_info, "info", "0")
    if tape_score == 0:
        tape_score = get_info_value(buy_info, "tape", "0")
    if short_pressure_score == 0:
        short_pressure_score = get_info_value(buy_info, "short", "0")

    available_cash = balance["orderable_cash"] or balance["cash_balance"] or Decimal("0")

    position = get_current_position(conn, account_id, ticker_code)
    latest_price = get_latest_price(conn, ticker_code)

    validation_reasons = build_common_validation(
        action_type="SELL",
        ticker_code=ticker_code,
        market_signal=market_signal,
        available_cash=available_cash,
        latest_price=latest_price,
        position=position,
        account_id=account_id,
        conn=conn,
    )

    current_qty = to_int(position.get("quantity"), 0)

    order_qty = current_qty
    order_price = latest_price
    target_amount = Decimal(order_qty) * latest_price if latest_price else Decimal("0")

    if order_qty <= 0:
        validation_reasons.append("order_qty <= 0")

    if validation_reasons:
        execution_status = "BLOCKED"
        block_reason = " / ".join(validation_reasons)
    else:
        execution_status = "READY"
        block_reason = None

    validation_result = {
        "validation_reasons": validation_reasons,
        "latest_price": str(latest_price) if latest_price is not None else None,
        "current_qty": current_qty,
        "current_eval_amount": str(position.get("eval_amount")),
        "source": "strategy_trade_log.sell_date",
    }

    position_size = get_info_value(buy_info, "position_size", "0")

    return {
        "execution_plan_id": plan_id,
        "source_run_id": trade["run_id"],
        "source_trade_log_id": trade["id"],
        "source_type": "TRADE_LOG_SELL",
        "execution_mode": "DRY_RUN",
        "account_id": account_id,
        "account_no": account_no,
        "signal_date": trade["sell_date"],
        "ticker_code": ticker_code,
        "stock_name": stock_name,
        "action_type": "SELL",
        "signal_type": "SELL",
        "signal_score": final_score,
        "signal_position_size": position_size,
        "market_signal": market_signal,
        "market_regime_score": None,
        "flow_score": flow_score,
        "info_score": info_score,
        "tape_score": tape_score,
        "final_score": final_score,
        "short_pressure_score": short_pressure_score,
        "target_weight": Decimal("0"),
        "target_amount": target_amount,
        "current_qty": current_qty,
        "current_eval_amount": position.get("eval_amount"),
        "order_qty": order_qty,
        "order_price": order_price,
        "order_method": "MARKET",
        "execution_status": execution_status,
        "block_reason": block_reason,
        "signal_reason": dumps_json({
            "buy_info": buy_info,
            "sell_info": sell_info,
            "return_pct": str(trade.get("return_pct")),
            "holding_period": trade.get("holding_period"),
            "sell_open_price": str(trade.get("sell_open_price")),
            "sell_close_price": str(trade.get("sell_close_price")),
            "sell_low_price": str(trade.get("sell_low_price")),
        }),
        "validation_result": dumps_json(validation_result),
    }


def build_execution_orders(conn, plan_id, account, balance, market_daily, buy_candidates, sell_candidates):
    """
    BUY 후보 + SELL 후보를 모두 strategy_execution_order 저장용 dict 목록으로 변환.
    """

    order_data_list = []

    for trade in buy_candidates:
        order_data_list.append(
            build_buy_execution_order(
                conn=conn,
                plan_id=plan_id,
                account=account,
                balance=balance,
                market_daily=market_daily,
                trade=trade,
            )
        )

    for trade in sell_candidates:
        order_data_list.append(
            build_sell_execution_order(
                conn=conn,
                plan_id=plan_id,
                account=account,
                balance=balance,
                market_daily=market_daily,
                trade=trade,
            )
        )

    return order_data_list
