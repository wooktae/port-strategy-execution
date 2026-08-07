"""
BUY 주문 후보의 주문 가능 금액과 수량을 계산하는 sizing helper.
목표 비중, 현금, 최소 주문 금액 기준을 다루며 DB나 외부 API에는 접근하지 않는다.
계산 정책 변경은 실제 주문 규모에 영향을 주므로 별도 검토가 필요하다.
"""

from decimal import Decimal, ROUND_DOWN


SIZING_METHOD_TOTAL_EVAL_REBALANCE_V1 = "TOTAL_EVAL_TARGET_REBALANCE_V1"
MARKET_BUY_CASH_RESERVE_RATIO = Decimal("1.10")
MARKET_BUY_CASH_RESERVE_POLICY = "ESTIMATED_ORDER_AMOUNT_110_PERCENT"


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


def floor_to_int(value):
    if value is None:
        return 0

    return int(
        to_decimal(value).to_integral_value(rounding=ROUND_DOWN)
    )


def calculate_buy_order_sizing(
    *,
    available_cash,
    total_eval_amount,
    position_size,
    latest_price,
    current_position_qty=0,
    current_position_eval_amount=0,
    min_order_amount=None,
    max_order_amount=None,
):
    """
    BUY 주문 수량 계산 전용 함수.

    목적:
    - Daily Signal의 position_size를 실제 계좌 기준 주문 수량으로 변환
    - 기존 available_cash * position_size 방식이 아니라,
      총 평가금액 기준 목표 보유금액 방식 사용

    산식:
    1) target_position_amount = total_eval_amount * position_size
    2) additional_buy_amount = target_position_amount - current_position_eval_amount
    3) capped_buy_amount = min(additional_buy_amount, available_cash, max_order_amount)
    4) effective_order_price = latest_price * 1.10
    5) order_qty = floor(capped_buy_amount / effective_order_price)
    6) required_cash_amount = estimated_order_amount * 1.10
    """

    validation_reasons = []

    available_cash = to_decimal(available_cash, "0")
    total_eval_amount = to_decimal(total_eval_amount, "0")
    position_size = to_decimal(position_size, "0")
    latest_price = to_decimal(latest_price, "0")
    current_position_qty = to_int(current_position_qty, 0)
    current_position_eval_amount = to_decimal(current_position_eval_amount, "0")

    min_order_amount_decimal = (
        to_decimal(min_order_amount, "0")
        if min_order_amount is not None
        else Decimal("0")
    )

    max_order_amount_decimal = (
        to_decimal(max_order_amount, "0")
        if max_order_amount is not None
        else None
    )

    if available_cash <= 0:
        validation_reasons.append("available_cash <= 0")

    if total_eval_amount <= 0:
        validation_reasons.append("total_eval_amount <= 0")

    if position_size <= 0:
        validation_reasons.append("position_size <= 0")

    if latest_price <= 0:
        validation_reasons.append("latest_price <= 0")

    if current_position_qty < 0:
        validation_reasons.append("current_position_qty < 0")

    if current_position_eval_amount < 0:
        validation_reasons.append("current_position_eval_amount < 0")

    if max_order_amount_decimal is not None and max_order_amount_decimal <= 0:
        validation_reasons.append("max_order_amount <= 0")

    target_position_amount = Decimal("0")
    additional_buy_amount = Decimal("0")
    capped_buy_amount = Decimal("0")
    order_qty = 0
    estimated_order_amount = Decimal("0")
    required_cash_amount = Decimal("0")
    effective_order_price = Decimal("0")

    if not validation_reasons:
        target_position_amount = total_eval_amount * position_size
        additional_buy_amount = target_position_amount - current_position_eval_amount

        if target_position_amount <= 0:
            validation_reasons.append("target_position_amount <= 0")

        if additional_buy_amount <= 0:
            validation_reasons.append("additional_buy_amount <= 0")

    if not validation_reasons:
        capped_buy_amount = min(additional_buy_amount, available_cash)

        if max_order_amount_decimal is not None:
            capped_buy_amount = min(capped_buy_amount, max_order_amount_decimal)

        if capped_buy_amount <= 0:
            validation_reasons.append("capped_buy_amount <= 0")

        if min_order_amount_decimal > 0 and capped_buy_amount < min_order_amount_decimal:
            validation_reasons.append("capped_buy_amount < min_order_amount")

    if not validation_reasons:
        effective_order_price = (
            latest_price * MARKET_BUY_CASH_RESERVE_RATIO
        )
        order_qty = int(
            (
                capped_buy_amount / effective_order_price
            ).to_integral_value(rounding=ROUND_DOWN)
        )

        if order_qty <= 0:
            validation_reasons.append(
                "order_qty <= 0 after market buy cash reserve"
            )

        estimated_order_amount = latest_price * Decimal(order_qty)
        required_cash_amount = (
            estimated_order_amount * MARKET_BUY_CASH_RESERVE_RATIO
        )

        if required_cash_amount > available_cash:
            validation_reasons.append(
                "required_cash_amount > available_cash"
            )

        if min_order_amount_decimal > 0 and estimated_order_amount < min_order_amount_decimal:
            validation_reasons.append("estimated_order_amount < min_order_amount")

    sizing_detail = {
        "sizing_method": SIZING_METHOD_TOTAL_EVAL_REBALANCE_V1,

        "available_cash": str(available_cash),
        "total_eval_amount": str(total_eval_amount),
        "position_size": str(position_size),
        "latest_price": str(latest_price),

        "current_position_qty": current_position_qty,
        "current_position_eval_amount": str(current_position_eval_amount),

        "target_position_amount": str(target_position_amount),
        "additional_buy_amount": str(additional_buy_amount),
        "capped_buy_amount": str(capped_buy_amount),

        "min_order_amount": str(min_order_amount_decimal),
        "max_order_amount": (
            str(max_order_amount_decimal)
            if max_order_amount_decimal is not None
            else None
        ),

        "order_qty": order_qty,
        "estimated_order_amount": str(estimated_order_amount),
        "required_cash_amount": str(required_cash_amount),
        "effective_order_price": str(effective_order_price),
        "market_buy_cash_reserve_ratio": str(
            MARKET_BUY_CASH_RESERVE_RATIO
        ),
        "market_buy_cash_reserve_policy": (
            MARKET_BUY_CASH_RESERVE_POLICY
        ),
        "validation_reasons": validation_reasons,
    }

    return {
        "order_qty": order_qty,
        "target_amount": capped_buy_amount,
        "estimated_order_amount": estimated_order_amount,
        "required_cash_amount": required_cash_amount,
        "market_buy_cash_reserve_ratio": (
            MARKET_BUY_CASH_RESERVE_RATIO
        ),
        "market_buy_cash_reserve_policy": (
            MARKET_BUY_CASH_RESERVE_POLICY
        ),
        "sizing_detail": sizing_detail,
        "validation_reasons": validation_reasons,
    }
