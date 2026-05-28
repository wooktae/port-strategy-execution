"""
포지션, 종목 feature, 시장 feature를 기준으로 SELL/HOLD 판단을 계산한다.
DB나 connector에는 접근하지 않는 순수 평가 helper 성격이지만 전략 판단 정책을 담고 있다.
점수 기준과 sell reason 변경은 전략 결과 변화로 이어지므로 별도 검토가 필요하다.
"""

from decimal import Decimal


# =========================================================
# 운영 SELL v1 설정값
# =========================================================
# 지금은 port_strategy_common.config의 SELL_CONFIG를 바로 물지 않고,
# 운영 실행 쪽에서 안전한 기본값으로 시작.
#
# 이유:
# - backtest sell_logic은 prev_close / today_close / raw_today_ret 구조
# - 운영 sell_logic은 entry_price / current_price / connector snapshot 구조
# - 입력 구조가 달라서 그대로 이식하면 위험함
# =========================================================

MIN_HOLDING_DAYS_FOR_NORMAL_SELL = 2

HARD_STOP_LOSS_RATE = Decimal("-0.10")
MAX_HOLDING_DAYS = 15

MARKET_BLOCK_KEEP_PROFIT = Decimal("0.02")
QUALITY_DROP_FLOW_THRESHOLD = Decimal("0.45")
QUALITY_DROP_FINAL_THRESHOLD = Decimal("0.35")

PROFIT_POSITION_RATE = Decimal("0.03")


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


def normalize_feature_value(row, key, default="0"):
    if not row:
        return Decimal(default)

    return to_decimal(row.get(key), default)


def normalize_market_signal(market_feature):
    """
    market feature에서 market signal을 최대한 안전하게 추출.
    현재 프로젝트에서는 아래 가능성이 있음:
    - strategy_backtest_daily.market_signal
    - decision signal type
    - pre_total_market_daily_feature 기반 평가 결과
    """

    if not market_feature:
        return "UNKNOWN"

    for key in (
        "market_signal",
        "signal_type",
        "market_mode",
        "decision_signal",
    ):
        value = market_feature.get(key)
        if value:
            return str(value).upper()

    return "UNKNOWN"


def build_base_sell_info(position_ctx, stock_feature, market_feature):
    """
    sell_info 기본 payload 생성.
    나중에 strategy_execution_order.sell_info와
    strategy_position_state.latest_sell_info에 저장할 수 있는 구조.
    """

    flow_score = normalize_feature_value(stock_feature, "flow_score")
    final_score = normalize_feature_value(stock_feature, "final_score")
    info_score = normalize_feature_value(stock_feature, "info_score")
    tape_score = normalize_feature_value(stock_feature, "tape_score")
    short_pressure_score = normalize_feature_value(stock_feature, "short_pressure_score")
    volatility_20d = normalize_feature_value(stock_feature, "volatility_20d")
    intraday_range = normalize_feature_value(stock_feature, "intraday_range")

    market_signal = normalize_market_signal(market_feature)
    market_regime_score = normalize_feature_value(market_feature, "market_regime_score")
    breadth_pressure_score = normalize_feature_value(market_feature, "breadth_pressure_score")
    flow_pressure_score = normalize_feature_value(market_feature, "flow_pressure_score")

    return {
        "version": "execution_sell_v1",
        "position_state_id": position_ctx.get("position_state_id"),
        "ticker_code": position_ctx.get("ticker_code"),
        "stock_name": position_ctx.get("stock_name"),

        "entry_date": str(position_ctx.get("entry_date")),
        "entry_price": str(position_ctx.get("entry_price")),
        "current_price": str(position_ctx.get("current_price")),
        "remaining_qty": to_int(position_ctx.get("remaining_qty")),
        "snapshot_qty": to_int(position_ctx.get("snapshot_qty")),
        "sellable_qty": to_int(position_ctx.get("sellable_qty")),
        "holding_days": to_int(position_ctx.get("holding_days")),

        "expected_pnl_rate": str(position_ctx.get("expected_pnl_rate")),
        "expected_pnl_amount": str(position_ctx.get("expected_pnl_amount")),

        "market_signal": market_signal,
        "market_regime_score": str(market_regime_score),
        "breadth_pressure_score": str(breadth_pressure_score),
        "flow_pressure_score": str(flow_pressure_score),

        "flow_score": str(flow_score),
        "final_score": str(final_score),
        "info_score": str(info_score),
        "tape_score": str(tape_score),
        "short_pressure_score": str(short_pressure_score),
        "volatility_20d": str(volatility_20d),
        "intraday_range": str(intraday_range),

        "validation_warnings": position_ctx.get("validation_warnings") or [],
        "rules": {
            "min_holding_days_for_normal_sell": MIN_HOLDING_DAYS_FOR_NORMAL_SELL,
            "hard_stop_loss_rate": str(HARD_STOP_LOSS_RATE),
            "max_holding_days": MAX_HOLDING_DAYS,
            "market_block_keep_profit": str(MARKET_BLOCK_KEEP_PROFIT),
            "quality_drop_flow_threshold": str(QUALITY_DROP_FLOW_THRESHOLD),
            "quality_drop_final_threshold": str(QUALITY_DROP_FINAL_THRESHOLD),
            "profit_position_rate": str(PROFIT_POSITION_RATE),
        },
    }


def make_result(
    *,
    action,
    reason,
    position_ctx,
    stock_feature,
    market_feature,
    detail=None,
):
    """
    action:
      - SELL
      - HOLD
      - SKIP

    reason:
      - SELL_HARD_STOP
      - HOLD_MIN_HOLDING_DAYS
      - SKIP_NOT_SELLABLE
      등
    """

    sell_info = build_base_sell_info(
        position_ctx=position_ctx,
        stock_feature=stock_feature,
        market_feature=market_feature,
    )

    sell_info["action"] = action
    sell_info["reason"] = reason

    if detail:
        sell_info["detail"] = detail

    return {
        "action": action,
        "reason": reason,
        "sell_info": sell_info,

        "position_state_id": position_ctx.get("position_state_id"),
        "ticker_code": position_ctx.get("ticker_code"),
        "stock_name": position_ctx.get("stock_name"),

        "order_qty": min(
            to_int(position_ctx.get("remaining_qty")),
            to_int(position_ctx.get("sellable_qty")),
        ),
        "expected_sell_price": position_ctx.get("current_price"),
        "expected_pnl_amount": position_ctx.get("expected_pnl_amount"),
        "expected_pnl_rate": position_ctx.get("expected_pnl_rate"),
    }


def evaluate_position_sell(position_ctx, stock_feature=None, market_feature=None):
    """
    운영용 SELL 판단 v1.

    주의:
    - 이 함수는 주문을 생성하지 않음.
    - DB도 수정하지 않음.
    - SELL/HOLD/SKIP 판단 결과만 반환.
    """

    stock_feature = stock_feature or {}
    market_feature = market_feature or {}

    remaining_qty = to_int(position_ctx.get("remaining_qty"))
    snapshot_qty = to_int(position_ctx.get("snapshot_qty"))
    sellable_qty = to_int(position_ctx.get("sellable_qty"))
    holding_days = to_int(position_ctx.get("holding_days"))

    current_price = to_decimal(position_ctx.get("current_price"))
    entry_price = to_decimal(position_ctx.get("entry_price"))
    pnl_rate = to_decimal(position_ctx.get("expected_pnl_rate"))
    pnl_amount = to_decimal(position_ctx.get("expected_pnl_amount"))

    validation_warnings = position_ctx.get("validation_warnings") or []

    flow_score = normalize_feature_value(stock_feature, "flow_score")
    final_score = normalize_feature_value(stock_feature, "final_score")
    short_pressure_score = normalize_feature_value(stock_feature, "short_pressure_score")

    market_signal = normalize_market_signal(market_feature)

    # -----------------------------------------------------
    # 0. 데이터/주문 가능성 검증
    # -----------------------------------------------------
    if remaining_qty <= 0:
        return make_result(
            action="SKIP",
            reason="SKIP_REMAINING_QTY_ZERO",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail="전략 포지션 remaining_qty가 0 이하라서 SELL 평가 제외",
        )

    if snapshot_qty <= 0:
        return make_result(
            action="SKIP",
            reason="SKIP_NO_BROKER_POSITION",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail="connector_position_snapshot 기준 실제 보유수량이 없어서 SELL 평가 제외",
        )

    if sellable_qty <= 0:
        return make_result(
            action="HOLD",
            reason="HOLD_NOT_SELLABLE",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail="실제 매도가능수량이 0이라서 SELL 후보 생성 보류",
        )

    if current_price <= 0 or entry_price <= 0:
        return make_result(
            action="SKIP",
            reason="SKIP_INVALID_PRICE",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail="현재가 또는 진입가가 0 이하라서 SELL 평가 제외",
        )

    # -----------------------------------------------------
    # 1. 손절은 보유일수와 무관하게 최우선
    # -----------------------------------------------------
    if pnl_rate <= HARD_STOP_LOSS_RATE:
        return make_result(
            action="SELL",
            reason="SELL_HARD_STOP",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail=f"평가손익률 {pnl_rate} <= hard stop {HARD_STOP_LOSS_RATE}",
        )

    # -----------------------------------------------------
    # 2. 최소 보유일수 보호
    #    현재 v1에서는 1일 이하는 일반 매도 금지.
    #    단, hard stop은 위에서 이미 통과.
    # -----------------------------------------------------
    if holding_days < MIN_HOLDING_DAYS_FOR_NORMAL_SELL:
        return make_result(
            action="HOLD",
            reason="HOLD_MIN_HOLDING_DAYS",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail=f"보유일수 {holding_days}일 < 최소 일반 매도일수 {MIN_HOLDING_DAYS_FOR_NORMAL_SELL}일",
        )

    # -----------------------------------------------------
    # 3. 최대 보유일수
    # -----------------------------------------------------
    if holding_days >= MAX_HOLDING_DAYS:
        return make_result(
            action="SELL",
            reason="SELL_MAX_HOLDING_DAYS",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail=f"보유일수 {holding_days}일 >= 최대 보유일수 {MAX_HOLDING_DAYS}일",
        )

    # -----------------------------------------------------
    # 4. 시장 BLOCK 조건
    #    market_signal이 BLOCK인데 이익이 충분하지 않으면 매도.
    # -----------------------------------------------------
    if market_signal == "BLOCK" and pnl_rate < MARKET_BLOCK_KEEP_PROFIT:
        return make_result(
            action="SELL",
            reason="SELL_MARKET_BLOCK_WEAK_PROFIT",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail=(
                f"market_signal=BLOCK이고 평가손익률 {pnl_rate} "
                f"< keep_profit {MARKET_BLOCK_KEEP_PROFIT}"
            ),
        )

    # -----------------------------------------------------
    # 5. 품질 저하
    #    flow/final이 동시에 약하면 매도.
    # -----------------------------------------------------
    if (
        flow_score < QUALITY_DROP_FLOW_THRESHOLD
        and final_score < QUALITY_DROP_FINAL_THRESHOLD
    ):
        return make_result(
            action="SELL",
            reason="SELL_QUALITY_DROP",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail=(
                f"flow_score {flow_score} < {QUALITY_DROP_FLOW_THRESHOLD}, "
                f"final_score {final_score} < {QUALITY_DROP_FINAL_THRESHOLD}"
            ),
        )

    # -----------------------------------------------------
    # 6. 공매도/숏 압력 보조 경고
    #    v1에서는 단독 SELL 조건으로 쓰지 않고 sell_info에만 기록.
    # -----------------------------------------------------
    short_warning = None
    if short_pressure_score >= Decimal("0.80"):
        short_warning = f"short_pressure_score 높음: {short_pressure_score}"

    # -----------------------------------------------------
    # 7. 수익권 포지션은 기본 보유
    # -----------------------------------------------------
    if pnl_rate >= PROFIT_POSITION_RATE:
        detail = f"평가손익률 {pnl_rate} >= 수익권 기준 {PROFIT_POSITION_RATE}"
        if short_warning:
            detail += f" / {short_warning}"

        return make_result(
            action="HOLD",
            reason="HOLD_PROFIT_POSITION",
            position_ctx=position_ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
            detail=detail,
        )

    # -----------------------------------------------------
    # 8. 기본 HOLD
    # -----------------------------------------------------
    detail = (
        f"기본 HOLD: pnl_rate={pnl_rate}, pnl_amount={pnl_amount}, "
        f"flow={flow_score}, final={final_score}, market_signal={market_signal}"
    )
    if validation_warnings:
        detail += f", warnings={validation_warnings}"
    if short_warning:
        detail += f", {short_warning}"

    return make_result(
        action="HOLD",
        reason="HOLD_DEFAULT",
        position_ctx=position_ctx,
        stock_feature=stock_feature,
        market_feature=market_feature,
        detail=detail,
    )
