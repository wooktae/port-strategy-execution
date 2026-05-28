# C:\Workspaces\port_strategy_execution\execution_sell_builder.py

"""
OPEN 포지션을 평가해 POSITION_SELL execution order 후보를 생성하는 builder/entrypoint.
position loader, sell evaluator, repository update를 결합하며 DB write가 발생할 수 있다.
운영 실행 순서와 포지션 상태 갱신 정책을 임의로 바꾸지 않는다.
"""

from decimal import Decimal

from execution_db import get_conn
from execution_repository import (
    get_account,
    get_latest_balance,
    get_latest_strategy_run,
    create_or_get_plan,
    update_plan_summary,
    mark_plan_no_candidate,
    get_latest_stock_feature_for_sell,
    get_latest_market_feature_for_sell,
    update_position_sell_evaluation,
    upsert_position_sell_execution_order,
    mark_position_sell_ready,
    dumps_json,
)
from execution_position_loader import load_position_contexts
from execution_sell_evaluator import evaluate_position_sell


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


def normalize_signal_score(stock_feature):
    if not stock_feature:
        return Decimal("0")

    return to_decimal(stock_feature.get("final_score"))


def normalize_signal_position_size(position_ctx):
    """
    SELL에서는 신규 target position size가 없다.
    현재 보유 포지션 비중을 signal_position_size로 기록한다.

    정확한 포트폴리오 비중은 나중에 balance 기준으로 개선 가능.
    지금은 buy_info의 signal_position_size를 우선 사용한다.
    """

    buy_info = position_ctx.get("buy_info") or {}

    if isinstance(buy_info, dict):
        value = buy_info.get("signal_position_size")
        if value is not None:
            return to_decimal(value)

    return Decimal("0")


def get_feature_value(row, key, default="0"):
    if not row:
        return Decimal(default)

    return to_decimal(row.get(key), default)


def get_market_signal(market_feature):
    if not market_feature:
        return None

    for key in (
        "market_signal",
        "signal_type",
        "market_mode",
        "decision_signal",
    ):
        value = market_feature.get(key)
        if value:
            return str(value)

    return None


def build_validation_result(evaluation_result, position_ctx):
    sell_info = evaluation_result.get("sell_info") or {}

    return {
        "source": "execution_sell_builder",
        "action": evaluation_result.get("action"),
        "reason": evaluation_result.get("reason"),
        "position_state_id": position_ctx.get("position_state_id"),
        "ticker_code": position_ctx.get("ticker_code"),
        "stock_name": position_ctx.get("stock_name"),
        "order_qty": evaluation_result.get("order_qty"),
        "expected_sell_price": str(evaluation_result.get("expected_sell_price")),
        "expected_pnl_amount": str(evaluation_result.get("expected_pnl_amount")),
        "expected_pnl_rate": str(evaluation_result.get("expected_pnl_rate")),
        "detail": sell_info.get("detail"),
        "validation_warnings": position_ctx.get("validation_warnings") or [],
    }


def build_position_sell_order_data(
    *,
    plan,
    latest_run,
    account,
    position_ctx,
    stock_feature,
    market_feature,
    evaluation_result,
):
    """
    evaluate_position_sell() 결과를 strategy_execution_order insert용 dict로 변환한다.
    """

    signal_score = normalize_signal_score(stock_feature)
    signal_position_size = normalize_signal_position_size(position_ctx)

    order_qty = to_int(evaluation_result.get("order_qty"))
    order_price = to_decimal(evaluation_result.get("expected_sell_price"))

    current_qty = to_int(position_ctx.get("snapshot_qty"))
    current_eval_amount = (
        to_decimal(position_ctx.get("current_price"))
        * Decimal(current_qty)
    )

    sell_info = evaluation_result.get("sell_info") or {}
    validation_result = build_validation_result(
        evaluation_result=evaluation_result,
        position_ctx=position_ctx,
    )

    flow_score = get_feature_value(stock_feature, "flow_score")
    info_score = get_feature_value(stock_feature, "info_score")
    tape_score = get_feature_value(stock_feature, "tape_score")
    final_score = get_feature_value(stock_feature, "final_score")
    short_pressure_score = get_feature_value(stock_feature, "short_pressure_score")

    market_regime_score = get_feature_value(market_feature, "market_regime_score")
    market_signal = get_market_signal(market_feature)

    return {
        "execution_plan_id": plan["id"],

        "source_run_id": latest_run["run_id"],
        "source_position_state_id": position_ctx["position_state_id"],
        "source_type": "POSITION_SELL",
        "execution_mode": DEFAULT_EXECUTION_MODE,

        "account_id": account["id"],
        "account_no": account["account_no"],
        "signal_date": plan["plan_date"],
        "ticker_code": position_ctx["ticker_code"],
        "stock_name": position_ctx["stock_name"],

        "action_type": "SELL",
        "signal_type": "SELL",
        "signal_score": signal_score,
        "signal_position_size": signal_position_size,

        "market_signal": market_signal,
        "market_regime_score": market_regime_score,
        "flow_score": flow_score,
        "info_score": info_score,
        "tape_score": tape_score,
        "final_score": final_score,
        "short_pressure_score": short_pressure_score,

        # SELL에서는 target_weight / target_amount를 0으로 둔다.
        "target_weight": Decimal("0"),
        "target_amount": Decimal("0"),
        "current_qty": current_qty,
        "current_eval_amount": current_eval_amount,

        "order_qty": order_qty,
        "order_price": order_price,
        "order_method": DEFAULT_ORDER_METHOD,

        "execution_status": "READY",
        "block_reason": None,
        "signal_reason": dumps_json({
            "source": "position_sell_evaluator",
            "reason": evaluation_result.get("reason"),
            "action": evaluation_result.get("action"),
            "detail": sell_info.get("detail"),
            "position_state_id": position_ctx.get("position_state_id"),
            "ticker_code": position_ctx.get("ticker_code"),
            "expected_pnl_rate": str(evaluation_result.get("expected_pnl_rate")),
            "expected_pnl_amount": str(evaluation_result.get("expected_pnl_amount")),
        }),
        "validation_result": dumps_json(validation_result),

        "sell_reason": evaluation_result.get("reason"),
        "sell_info": dumps_json(sell_info),
        "expected_sell_price": evaluation_result.get("expected_sell_price"),
        "expected_pnl_amount": evaluation_result.get("expected_pnl_amount"),
        "expected_pnl_rate": evaluation_result.get("expected_pnl_rate"),
    }


def build_position_sell_orders(conn, *, plan, latest_run, account):
    """
    운영 포지션 기반 SELL 후보 생성.

    반환:
    {
      "evaluated_count": int,
      "sell_created_count": int,
      "hold_count": int,
      "skip_count": int,
      "orders": list,
      "evaluations": list
    }
    """

    contexts = load_position_contexts(
        conn=conn,
        account_id=account["id"],
        plan_date=plan["plan_date"],
    )

    result_summary = {
        "evaluated_count": 0,
        "sell_created_count": 0,
        "hold_count": 0,
        "skip_count": 0,
        "orders": [],
        "evaluations": [],
    }

    for ctx in contexts:
        ticker_code = ctx["ticker_code"]

        stock_feature = get_latest_stock_feature_for_sell(
            conn=conn,
            ticker_code=ticker_code,
            plan_date=plan["plan_date"],
        )

        market_feature = get_latest_market_feature_for_sell(
            conn=conn,
            plan_date=plan["plan_date"],
        )

        evaluation = evaluate_position_sell(
            position_ctx=ctx,
            stock_feature=stock_feature,
            market_feature=market_feature,
        )

        result_summary["evaluated_count"] += 1
        result_summary["evaluations"].append(evaluation)

        update_position_sell_evaluation(
            conn=conn,
            position_state_id=ctx["position_state_id"],
            plan_date=plan["plan_date"],
            evaluation_result=evaluation,
        )

        action = evaluation.get("action")

        if action == "SELL":
            order_data = build_position_sell_order_data(
                plan=plan,
                latest_run=latest_run,
                account=account,
                position_ctx=ctx,
                stock_feature=stock_feature,
                market_feature=market_feature,
                evaluation_result=evaluation,
            )

            order = upsert_position_sell_execution_order(
                conn=conn,
                order_data=order_data,
            )

            mark_position_sell_ready(
                conn=conn,
                position_state_id=ctx["position_state_id"],
                evaluation_result=evaluation,
            )

            result_summary["sell_created_count"] += 1
            result_summary["orders"].append(order)

        elif action == "HOLD":
            result_summary["hold_count"] += 1

        else:
            result_summary["skip_count"] += 1

    return result_summary


def print_header(title):
    print()
    print("========================================")
    print(title)
    print("========================================")


def print_evaluation(evaluation):
    sell_info = evaluation.get("sell_info") or {}

    print()
    print("----------------------------------------")
    print(f"position_state_id : {evaluation.get('position_state_id')}")
    print(f"ticker            : {evaluation.get('ticker_code')} / {evaluation.get('stock_name')}")
    print(f"action            : {evaluation.get('action')}")
    print(f"reason            : {evaluation.get('reason')}")
    print(f"order_qty         : {evaluation.get('order_qty')}")
    print(f"expected_price    : {evaluation.get('expected_sell_price')}")
    print(f"expected_pnl_amt  : {evaluation.get('expected_pnl_amount')}")
    print(f"expected_pnl_rate : {evaluation.get('expected_pnl_rate')}")
    print(f"detail            : {sell_info.get('detail')}")


def main():
    conn = get_conn()
    conn.autocommit = False

    try:
        account = get_account(conn)
        balance = get_latest_balance(conn, account["id"])
        latest_run = get_latest_strategy_run(conn)

        # 운영 SELL 테스트 기준:
        # 현재는 최신 잔고일(balance.as_of_date)을 plan_date로 사용한다.
        #
        # 과거 테스트에서는 2026-04-30 snapshot + 2026-04-29 feature 조합을 사용했었다.
        # backtest_execution_run과 통합할 때는 plan_date 인자를 받을 예정.
        plan_date = balance["as_of_date"]

        market_feature = get_latest_market_feature_for_sell(
            conn=conn,
            plan_date=plan_date,
        )

        market_daily_for_plan = {
            "date": plan_date,
            "market_signal": (
                market_feature.get("market_signal")
                if market_feature and market_feature.get("market_signal")
                else "UNKNOWN"
            ),
            "position_count": None,
            "daily_return": None,
            "cum_return": None,
        }

        plan_id = create_or_get_plan(
            conn=conn,
            account=account,
            balance=balance,
            latest_run=latest_run,
            market_daily=market_daily_for_plan,
        )

        plan = {
            "id": plan_id,
            "plan_date": plan_date,
        }

        summary = build_position_sell_orders(
            conn=conn,
            plan=plan,
            latest_run=latest_run,
            account=account,
        )

        if summary["evaluated_count"] == 0:
            mark_plan_no_candidate(conn, plan["id"])
        else:
            update_plan_summary(conn, plan["id"])

        conn.commit()

        print_header("[Position SELL Builder Result]")
        print(f"plan_id            : {plan['id']}")
        print(f"plan_date          : {plan['plan_date']}")
        print(f"evaluated_count    : {summary['evaluated_count']}")
        print(f"sell_created_count : {summary['sell_created_count']}")
        print(f"hold_count         : {summary['hold_count']}")
        print(f"skip_count         : {summary['skip_count']}")

        for evaluation in summary["evaluations"]:
            print_evaluation(evaluation)

        if summary["orders"]:
            print_header("[Created SELL Orders]")
            for order in summary["orders"]:
                print(order)

    except Exception as e:
        conn.rollback()
        print()
        print("[ERROR] Position SELL builder 실패")
        print(e)
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
