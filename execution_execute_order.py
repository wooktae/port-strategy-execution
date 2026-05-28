"""
단일 strategy_execution_order를 지정해 수동으로 connector 주문을 실행하는 entrypoint.
execution mode 검증, connector BUY/SELL 호출, 주문 결과 DB 반영 경로가 있다.
--execute 사용 여부와 관계없이 일부 DB update가 가능하므로 승인 없이 실행하지 않는다.
"""

import argparse
import sys
from pathlib import Path

from execution_db import get_conn
from execution_config import STRATEGY_NAME, STRATEGY_VERSION
from execution_repository import (
    get_execution_order_for_execute,
    mark_execution_order_execution_mode,
    mark_execution_order_submitted,
    mark_execution_order_execute_failed,
    mark_position_sell_ordered,
)

# -------------------------------------------------
# Market Connector import path
# -------------------------------------------------
CONNECTOR_PATH = Path(r"C:\Workspaces\port-marketconnector").resolve()

if not CONNECTOR_PATH.exists():
    raise RuntimeError(f"Market Connector 경로가 없음: {CONNECTOR_PATH}")

sys.path.insert(0, str(CONNECTOR_PATH))

try:
    from connector_buy import buy_stock  # noqa: E402
    from connector_sell import sell_stock  # noqa: E402
except ModuleNotFoundError as e:
    print("[IMPORT ERROR]")
    print(f"CONNECTOR_PATH = {CONNECTOR_PATH}")
    print(f"sys.path[0]    = {sys.path[0]}")
    print("connector_buy.py / connector_sell.py 파일이 C:\\Workspaces\\port-marketconnector 아래에 있는지 확인 필요")
    raise e


# =================================================
# Execution Mode Policy
# =================================================

EXECUTION_MODE_DRY_RUN = "DRY_RUN"
EXECUTION_MODE_MANUAL_TEST = "MANUAL_TEST"
EXECUTION_MODE_PAPER_STRATEGY = "PAPER_STRATEGY"
EXECUTION_MODE_LIVE_STRATEGY = "LIVE_STRATEGY"

SUPPORTED_EXECUTION_MODES = {
    EXECUTION_MODE_DRY_RUN,
    EXECUTION_MODE_MANUAL_TEST,
    EXECUTION_MODE_PAPER_STRATEGY,
    EXECUTION_MODE_LIVE_STRATEGY,
}

MANUAL_TEST_MAX_QTY = 1


def print_header(title):
    print()
    print("========================================")
    print(title)
    print("========================================")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Execute strategy execution order by execution mode"
    )

    parser.add_argument(
        "--execution-order-id",
        required=True,
        type=int,
        help="실행할 strategy_execution_order.id",
    )

    parser.add_argument(
        "--execution-mode",
        required=False,
        choices=sorted(SUPPORTED_EXECUTION_MODES),
        help=(
            "실행 모드. "
            "미지정 시 DB의 execution_mode 사용. "
            "MANUAL_TEST=1주 제한, PAPER_STRATEGY=전략 수량 paper 실행, "
            "LIVE_STRATEGY=전략 수량 live 실행"
        ),
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제 connector BUY/SELL 주문 실행. 없으면 검증 및 execution_mode 변경만 수행",
    )

    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="LIVE_STRATEGY 실행 시 필수 안전 확인 플래그",
    )

    return parser.parse_args()


def to_int(value, default=0):
    if value is None:
        return default

    try:
        return int(value)
    except Exception:
        return default


def to_float_or_none(value):
    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


def resolve_execution_mode(order, requested_execution_mode):
    """
    CLI에서 execution_mode를 받으면 그 값을 우선 사용.
    없으면 DB에 저장된 execution_mode 사용.
    DB에도 없으면 DRY_RUN으로 처리.
    """

    execution_mode = requested_execution_mode or order.get("execution_mode") or EXECUTION_MODE_DRY_RUN

    if execution_mode not in SUPPORTED_EXECUTION_MODES:
        raise RuntimeError(f"지원하지 않는 execution_mode: {execution_mode}")

    return execution_mode


def build_sizing_policy(order, execution_mode):
    """
    전략 수량(order_qty)을 실제 connector 전송 수량(executed_order_qty)으로 변환.

    핵심:
    - DRY_RUN: 실제 전송 없음
    - MANUAL_TEST: 기존처럼 최대 1주만 전송
    - PAPER_STRATEGY: 전략 수량 그대로 paper 전송
    - LIVE_STRATEGY: 전략 수량 그대로 live 전송
    """

    strategy_order_qty = to_int(order.get("order_qty"), 0)

    if strategy_order_qty <= 0:
        return {
            "execution_mode": execution_mode,
            "strategy_order_qty": strategy_order_qty,
            "executed_order_qty": 0,
            "sizing_policy": "INVALID_STRATEGY_ORDER_QTY",
            "manual_test_max_qty": MANUAL_TEST_MAX_QTY,
            "is_connector_executable": False,
        }

    if execution_mode == EXECUTION_MODE_DRY_RUN:
        executed_order_qty = 0
        sizing_policy = "DRY_RUN_NO_CONNECTOR_EXECUTION"
        is_connector_executable = False

    elif execution_mode == EXECUTION_MODE_MANUAL_TEST:
        executed_order_qty = min(MANUAL_TEST_MAX_QTY, strategy_order_qty)
        sizing_policy = "MANUAL_TEST_MAX_1_SHARE"
        is_connector_executable = True

    elif execution_mode == EXECUTION_MODE_PAPER_STRATEGY:
        executed_order_qty = strategy_order_qty
        sizing_policy = "PAPER_STRATEGY_FULL_STRATEGY_QTY"
        is_connector_executable = True

    elif execution_mode == EXECUTION_MODE_LIVE_STRATEGY:
        executed_order_qty = strategy_order_qty
        sizing_policy = "LIVE_STRATEGY_FULL_STRATEGY_QTY"
        is_connector_executable = True

    else:
        raise RuntimeError(f"지원하지 않는 execution_mode: {execution_mode}")

    return {
        "execution_mode": execution_mode,
        "strategy_order_qty": strategy_order_qty,
        "executed_order_qty": executed_order_qty,
        "sizing_policy": sizing_policy,
        "manual_test_max_qty": MANUAL_TEST_MAX_QTY,
        "is_connector_executable": is_connector_executable,
    }


def validate_common(order):
    reasons = []

    if order["execution_status"] != "READY":
        reasons.append(f"READY 상태가 아님: execution_status={order['execution_status']}")

    if order["connector_order_request_id"] is not None:
        reasons.append(
            f"이미 connector_order_request_id가 있음: {order['connector_order_request_id']}"
        )

    if order["action_type"] not in ("BUY", "SELL"):
        reasons.append(f"BUY/SELL만 허용: action_type={order['action_type']}")

    if order["order_qty"] is None or to_int(order["order_qty"]) <= 0:
        reasons.append(f"주문수량이 0 이하: order_qty={order['order_qty']}")

    if order["order_price"] is None:
        reasons.append("order_price 없음")

    if not order["ticker_code"]:
        reasons.append("ticker_code 없음")

    if not order["account_no"]:
        reasons.append("account_no 없음")

    return reasons


def validate_environment(order, execution_mode, confirm_live):
    reasons = []

    environment = order.get("environment")

    if execution_mode in (
        EXECUTION_MODE_DRY_RUN,
        EXECUTION_MODE_MANUAL_TEST,
        EXECUTION_MODE_PAPER_STRATEGY,
    ):
        if environment != "paper":
            reasons.append(
                f"{execution_mode}는 paper 환경에서만 허용: environment={environment}"
            )

    elif execution_mode == EXECUTION_MODE_LIVE_STRATEGY:
        if environment != "live":
            reasons.append(
                f"LIVE_STRATEGY는 live 환경에서만 허용: environment={environment}"
            )

        if not confirm_live:
            reasons.append("LIVE_STRATEGY 실행에는 --confirm-live 필요")

    return reasons


def validate_sizing_policy(sizing_policy, execute):
    reasons = []

    if sizing_policy["strategy_order_qty"] <= 0:
        reasons.append(
            f"전략 주문수량이 0 이하: strategy_order_qty={sizing_policy['strategy_order_qty']}"
        )

    if execute:
        if not sizing_policy["is_connector_executable"]:
            reasons.append(
                f"{sizing_policy['execution_mode']} 모드는 connector 실제 실행 불가"
            )

        if sizing_policy["executed_order_qty"] <= 0:
            reasons.append(
                f"실제 전송 수량이 0 이하: executed_order_qty={sizing_policy['executed_order_qty']}"
            )

    return reasons


def validate_for_execution(order, execution_mode, sizing_policy, execute, confirm_live):
    reasons = []

    reasons.extend(validate_common(order))
    reasons.extend(validate_environment(order, execution_mode, confirm_live))
    reasons.extend(validate_sizing_policy(sizing_policy, execute))

    return reasons


def print_order(order, execution_mode, sizing_policy):
    print_header("[Execution Order Check]")
    print(f"execution_order_id  : {order['id']}")
    print(f"account_no          : {order['account_no']}")
    print(f"environment         : {order['environment']}")
    print(f"source_type         : {order['source_type']}")
    print(f"db_execution_mode   : {order['execution_mode']}")
    print(f"run_execution_mode  : {execution_mode}")
    print(f"action_type         : {order['action_type']}")
    print(f"ticker              : {order['ticker_code']} / {order['stock_name']}")
    print(f"strategy_order_qty  : {sizing_policy['strategy_order_qty']}")
    print(f"executed_order_qty  : {sizing_policy['executed_order_qty']}")
    print(f"sizing_policy       : {sizing_policy['sizing_policy']}")
    print(f"order_price         : {order['order_price']}")
    print(f"execution_status    : {order['execution_status']}")
    print(f"connector_order_id  : {order['connector_order_request_id']}")


def build_connector_kwargs(order, executed_order_qty):
    return {
        "stock_code": order["ticker_code"],
        "qty": executed_order_qty,
        "order_method": "MARKET",
        "order_price": None,
        "stock_name": order["stock_name"],
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "strategy_run_id": str(order["source_run_id"]) if order["source_run_id"] else None,
        "strategy_signal_id": None,
        "signal_date": str(order["signal_date"]),
        "signal_type": order["action_type"],
        "signal_score": to_float_or_none(order["signal_score"]),
        "signal_position_size": to_float_or_none(order["signal_position_size"]),
    }


def build_result_payload(order, execution_mode, sizing_policy, connector_result=None, error=None):
    payload = {
        "request_type": order["action_type"],
        "execution_mode": execution_mode,

        # 핵심 추적 필드
        "strategy_order_qty": sizing_policy["strategy_order_qty"],
        "executed_order_qty": sizing_policy["executed_order_qty"],
        "sizing_policy": sizing_policy["sizing_policy"],

        # 기존 추적 호환용
        "manual_test_qty": (
            sizing_policy["executed_order_qty"]
            if execution_mode == EXECUTION_MODE_MANUAL_TEST
            else None
        ),

        "manual_test_max_qty": sizing_policy["manual_test_max_qty"],
        "is_connector_executable": sizing_policy["is_connector_executable"],

        # 주문 컨텍스트
        "source_type": order.get("source_type"),
        "source_run_id": str(order["source_run_id"]) if order.get("source_run_id") else None,
        "source_trade_log_id": order.get("source_trade_log_id"),
        "source_position_state_id": order.get("source_position_state_id"),
        "ticker_code": order.get("ticker_code"),
        "stock_name": order.get("stock_name"),
        "order_price": str(order["order_price"]) if order.get("order_price") is not None else None,
        "target_amount": str(order["target_amount"]) if order.get("target_amount") is not None else None,
        "signal_position_size": (
            str(order["signal_position_size"])
            if order.get("signal_position_size") is not None
            else None
        ),
        "environment": order.get("environment"),
        "order_method": order.get("order_method"),
    }

    if connector_result is not None:
        payload["connector_result"] = connector_result

    if error is not None:
        payload["error"] = error

    return payload


def execute_connector_order(order, sizing_policy):
    """
    action_type에 따라 connector BUY 또는 SELL API를 호출한다.
    실제 주문 요청으로 이어지는 함수이므로 검증/문서화 작업에서는 호출하지 않는다.
    """
    action_type = order["action_type"]
    executed_order_qty = sizing_policy["executed_order_qty"]

    print_header(f"[CONNECTOR {action_type} EXECUTE]")
    print(f"ticker       : {order['ticker_code']} / {order['stock_name']}")
    print(f"qty          : {executed_order_qty}")
    print(f"method       : MARKET")
    print(f"policy       : {sizing_policy['sizing_policy']}")

    common_kwargs = build_connector_kwargs(
        order=order,
        executed_order_qty=executed_order_qty,
    )

    if action_type == "BUY":
        return buy_stock(**common_kwargs)

    if action_type == "SELL":
        return sell_stock(**common_kwargs)

    raise RuntimeError(f"지원하지 않는 action_type: {action_type}")


def main():
    args = parse_args()

    conn = get_conn()
    conn.autocommit = False

    try:
        # -------------------------------------------------
        # 1. Execution Order 조회
        # -------------------------------------------------
        order = get_execution_order_for_execute(
            conn,
            args.execution_order_id,
        )

        # -------------------------------------------------
        # 2. 실행 모드 / 수량 정책 결정
        # -------------------------------------------------
        execution_mode = resolve_execution_mode(
            order=order,
            requested_execution_mode=args.execution_mode,
        )

        sizing_policy = build_sizing_policy(
            order=order,
            execution_mode=execution_mode,
        )

        print_order(
            order=order,
            execution_mode=execution_mode,
            sizing_policy=sizing_policy,
        )

        # -------------------------------------------------
        # 3. 검증
        # -------------------------------------------------
        reasons = validate_for_execution(
            order=order,
            execution_mode=execution_mode,
            sizing_policy=sizing_policy,
            execute=args.execute,
            confirm_live=args.confirm_live,
        )

        if reasons:
            print_header("[BLOCKED]")
            for reason in reasons:
                print(f"- {reason}")
            conn.rollback()
            return

        # -------------------------------------------------
        # 4. execution_mode 명시적 저장
        # -------------------------------------------------
        updated = mark_execution_order_execution_mode(
            conn=conn,
            execution_order_id=args.execution_order_id,
            execution_mode=execution_mode,
        )
        conn.commit()

        print_header("[EXECUTION MODE READY]")
        print(f"id                 : {updated['id']}")
        print(f"execution_mode     : {updated['execution_mode']}")
        print(f"execution_status   : {updated['execution_status']}")
        print(f"connector_order_id : {updated['connector_order_request_id']}")

        # -------------------------------------------------
        # 5. 검증만 수행
        # -------------------------------------------------
        if not args.execute:
            print()
            print("검증 및 execution_mode 설정 완료. 실제 주문 실행은 --execute 필요.")
            print()
            print("[Mode Summary]")
            print("- DRY_RUN        : Connector 주문 없음")
            print("- MANUAL_TEST    : paper 1주 제한 주문")
            print("- PAPER_STRATEGY : paper 전략 수량 주문")
            print("- LIVE_STRATEGY  : live 전략 수량 주문, --confirm-live 필요")
            return

        # -------------------------------------------------
        # 6. Connector 실제 주문 호출
        # -------------------------------------------------
        result = execute_connector_order(
            order=order,
            sizing_policy=sizing_policy,
        )

        conn.close()

        # -------------------------------------------------
        # 7. Connector 결과 저장
        # -------------------------------------------------
        conn = get_conn()
        conn.autocommit = False

        if not result or not result.get("order_request_id"):
            failed_payload = build_result_payload(
                order=order,
                execution_mode=execution_mode,
                sizing_policy=sizing_policy,
                connector_result=result,
                error=f"connector {order['action_type']} result is empty",
            )

            failed = mark_execution_order_execute_failed(
                conn,
                args.execution_order_id,
                failed_payload,
            )
            conn.commit()

            print_header("[FAILED]")
            print(f"id               : {failed['id']}")
            print(f"execution_status : {failed['execution_status']}")
            print(result)
            return

        submitted_payload = build_result_payload(
            order=order,
            execution_mode=execution_mode,
            sizing_policy=sizing_policy,
            connector_result=result,
        )

        submitted = mark_execution_order_submitted(
            conn,
            args.execution_order_id,
            result["order_request_id"],
            submitted_payload,
        )

        if order["action_type"] == "SELL" and order.get("source_position_state_id"):
            mark_position_sell_ordered(
                conn,
                order["source_position_state_id"],
            )

        conn.commit()

        print_header("[SUBMITTED]")
        print(f"id                         : {submitted['id']}")
        print(f"execution_status           : {submitted['execution_status']}")
        print(f"execution_mode             : {submitted['execution_mode']}")
        print(f"connector_order_request_id : {submitted['connector_order_request_id']}")
        print(f"broker_order_no            : {result.get('broker_order_no')}")
        print(f"broker_branch_code         : {result.get('broker_branch_code')}")
        print(f"strategy_order_qty         : {sizing_policy['strategy_order_qty']}")
        print(f"executed_order_qty         : {sizing_policy['executed_order_qty']}")
        print(f"sizing_policy              : {sizing_policy['sizing_policy']}")

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
