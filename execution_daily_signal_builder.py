# C:\Workspaces\port_strategy_execution\execution_daily_signal_builder.py

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
    종목별 최대 주문금액 계산.

    현재 정책:
    - 총 평가금액의 50%를 단일 주문 상한으로 사용
    - 추후 execution_config.DEFAULT_MAX_ORDER_AMOUNT_RATIO로 이전 가능
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


def build_daily_signal_buy_execution_order(conn, plan_id, account, balance, daily_run, signal):
    """
    strategy_daily_signal row를 BUY execution candidate로 변환.

    핵심:
    - BUY 판단 / position_size는 Daily Signal에서 이미 결정됨
    - 여기서는 실제 계좌 기준 주문 수량으로 변환
    - 수량 계산은 execution_buy_sizing.calculate_buy_order_sizing()에 위임
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

    available_cash = (
        get_balance_value(balance, "orderable_cash", "0")
        or get_balance_value(balance, "cash_balance", "0")
        or Decimal("0")
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
    # 1. 공통 실행 후보 검증
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
    # 2. BUY 주문 수량 계산
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
    sizing_detail = sizing_result["sizing_detail"]

    # -------------------------------------------------
    # 3. Execution 상태 결정
    # -------------------------------------------------
    if validation_reasons:
        execution_status = "BLOCKED"
        block_reason = " / ".join(validation_reasons)
    else:
        execution_status = "READY"
        block_reason = None

    # -------------------------------------------------
    # 4. validation_result 저장
    # -------------------------------------------------
    validation_result = {
        "validation_reasons": validation_reasons,

        # 신규 구조: View / 운영 화면에서 구조적으로 표시하기 좋게 분리
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

        # 기존 호환 / SQL 조회 편의용 flat fields
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

        "execution_status": execution_status,
        "block_reason": block_reason,

        "signal_reason": dumps_json(signal_reason),
        "validation_result": dumps_json(validation_result),
    }


def build_daily_signal_execution_orders(conn, plan_id, account, balance, daily_run, signals):
    order_data_list = []

    for signal in signals:
        order_data_list.append(
            build_daily_signal_buy_execution_order(
                conn=conn,
                plan_id=plan_id,
                account=account,
                balance=balance,
                daily_run=daily_run,
                signal=signal,
            )
        )

    return order_data_list