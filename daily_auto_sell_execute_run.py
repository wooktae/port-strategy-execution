"""
READY 상태의 SELL execution order를 MarketConnector SELL 실행 요청으로 표시하는 entrypoint.
Strategy Execution은 실제 주문 제출 없이 REQUESTED 상태 전환까지만 수행한다.
자동 매도 요청 경로이므로 명시 승인과 대상 환경 확인 없이 실행하지 않는다.
"""

import argparse
import sys
from pathlib import Path
from datetime import date, datetime, timezone

from execution_db import get_conn
from execution_repository import (
    get_ready_daily_position_sell_execution_orders,
    get_latest_connector_position_snapshot,
    mark_execution_order_execution_mode,
    mark_execution_order_requested,
)


EXECUTION_MODE_PAPER_STRATEGY = "PAPER_STRATEGY"
SIZING_POLICY = "PAPER_STRATEGY_FULL_STRATEGY_QTY"
SUPPORTED_AUTO_SELL_SOURCE_TYPES = {
    "DAILY_POSITION_SELL",
    "INTRADAY_STOP_SELL",
}

# -------------------------------------------------
# Korean business day guard
# -------------------------------------------------
def _load_kr_holiday_checker():
    """
    port-interest-crawler / port_interest_crawler 쪽의 interest_get_holidays.py를
    사용할 수 있으면 한국 휴장일/공휴일 판정을 함께 사용한다.
    없으면 주말 판정만 수행한다.
    """
    candidate_paths = [
        Path(r"C:\Workspaces\port-interest-crawler"),
        Path(r"C:\Workspaces\port_interest_crawler"),
    ]

    for path in candidate_paths:
        try:
            if path.exists() and str(path) not in sys.path:
                sys.path.insert(0, str(path))

            from interest_get_holidays import is_holiday  # noqa: WPS433
            return is_holiday
        except Exception:
            continue

    return None


def is_kr_business_day(target_date=None):
    target_date = target_date or date.today()

    if target_date.weekday() >= 5:
        return False, "WEEKEND"

    holiday_checker = _load_kr_holiday_checker()

    if holiday_checker is not None:
        try:
            if holiday_checker(target_date, "KR"):
                return False, "KR_HOLIDAY"
        except Exception:
            # 휴일 유틸 오류 때문에 배치를 죽이지는 않고, 주말 판정만 신뢰한다.
            pass

    return True, "BUSINESS_DAY"


def print_non_business_day_no_target(step_name):
    today = date.today()
    is_business_day, reason = is_kr_business_day(today)

    if is_business_day:
        return False

    print_header(f"[{step_name} Blocked]")
    print(f"today  : {today}")
    print(f"reason : {reason}")
    print("[NO_TARGET] 한국 영업일이 아니므로 주문 관련 처리를 실행하지 않습니다.")
    print("connector_order_request를 생성하지 않고 종료합니다.")

    return True



def print_header(title):
    print()
    print("========================================")
    print(title)
    print("========================================")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Auto execute READY Daily/Intraday SELL orders in PAPER_STRATEGY mode"
    )

    parser.add_argument(
        "--plan-id",
        required=False,
        type=int,
        help="특정 execution_plan_id만 자동매도 실행",
    )

    parser.add_argument(
        "--limit",
        required=False,
        type=int,
        default=20,
        help="자동매도 대상 최대 건수",
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="MarketConnector SELL 실행 요청 등록. 없으면 조회/검증만 수행",
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


def validate_auto_sell_order(order):
    reasons = []

    if order["environment"] != "paper":
        reasons.append(f"paper 환경이 아님: environment={order['environment']}")

    if order["source_type"] not in SUPPORTED_AUTO_SELL_SOURCE_TYPES:
        reasons.append(
            f"자동매도 허용 source_type이 아님: source_type={order['source_type']}"
        )

    if order["action_type"] != "SELL":
        reasons.append(f"SELL이 아님: action_type={order['action_type']}")

    if order["execution_status"] != "READY":
        reasons.append(f"READY 상태가 아님: execution_status={order['execution_status']}")

    if order["connector_order_request_id"] is not None:
        reasons.append(
            f"이미 connector_order_request_id가 있음: {order['connector_order_request_id']}"
        )

    if order["execution_mode"] not in ("DRY_RUN", "PAPER_STRATEGY"):
        reasons.append(f"자동매도 허용 execution_mode가 아님: {order['execution_mode']}")

    order_qty = to_int(order.get("order_qty"))
    if order_qty <= 0:
        reasons.append(f"order_qty가 0 이하임: order_qty={order.get('order_qty')}")

    current_qty = to_int(order.get("current_qty"))
    if current_qty <= 0:
        reasons.append(f"current_qty가 0 이하임: current_qty={order.get('current_qty')}")

    if order_qty > current_qty:
        reasons.append(
            f"order_qty가 current_qty보다 큼: order_qty={order_qty}, current_qty={current_qty}"
        )

    if not order.get("account_no"):
        reasons.append("account_no 없음")

    if not order.get("ticker_code"):
        reasons.append("ticker_code 없음")

    return reasons

def validate_latest_sellable_quantity(conn, order):
    """
    MarketConnector SELL 실행 요청 등록 전에 최신 connector_position_snapshot 기준으로
    매도가능수량을 다시 확인한다.

    방어 목적:
    - READY 후보 생성 이후 실제 보유/매도가능수량이 바뀐 경우 차단
    - sellable_quantity 0인데 주문 나가는 상황 방지
    - order_qty > 최신 매도가능수량이면 주문 차단
    """

    snapshot = get_latest_connector_position_snapshot(
        conn=conn,
        account_id=order["account_id"],
        ticker_code=order["ticker_code"],
    )

    strategy_order_qty = to_int(order.get("order_qty"))

    if not snapshot:
        return {
            "ok": False,
            "reason": "LATEST_CONNECTOR_POSITION_SNAPSHOT_NOT_FOUND",
            "strategy_order_qty": strategy_order_qty,
            "latest_quantity": 0,
            "latest_sellable_quantity": 0,
            "snapshot": None,
        }

    latest_quantity = to_int(snapshot.get("quantity"))
    latest_sellable_quantity = to_int(snapshot.get("sellable_quantity"))

    result = {
        "ok": True,
        "reason": "OK",
        "strategy_order_qty": strategy_order_qty,
        "latest_quantity": latest_quantity,
        "latest_sellable_quantity": latest_sellable_quantity,
        "snapshot": {
            "id": snapshot.get("id"),
            "account_id": snapshot.get("account_id"),
            "account_no": snapshot.get("account_no"),
            "ticker_code": snapshot.get("ticker_code"),
            "stock_name": snapshot.get("stock_name"),
            "quantity": str(snapshot.get("quantity")),
            "sellable_quantity": str(snapshot.get("sellable_quantity")),
            "current_price": str(snapshot.get("current_price")),
            "eval_amount": str(snapshot.get("eval_amount")),
            "as_of_date": str(snapshot.get("as_of_date")),
            "as_of_ts": str(snapshot.get("as_of_ts")),
        },
    }

    if strategy_order_qty <= 0:
        result["ok"] = False
        result["reason"] = "STRATEGY_ORDER_QTY_ZERO"
        return result

    if latest_quantity <= 0:
        result["ok"] = False
        result["reason"] = "LATEST_POSITION_QTY_ZERO"
        return result

    if latest_sellable_quantity <= 0:
        result["ok"] = False
        result["reason"] = "LATEST_SELLABLE_QTY_ZERO"
        return result

    if strategy_order_qty > latest_sellable_quantity:
        result["ok"] = False
        result["reason"] = "ORDER_QTY_GT_LATEST_SELLABLE_QTY"
        return result

    return result

def build_result_payload(order, latest_sellable_check=None):
    return {
        "source": "daily_auto_sell_execute_run",
        "action": "REQUEST_MARKETCONNECTOR_SELL",
        "execution_order_id": order.get("id"),
        "ticker_code": order.get("ticker_code"),
        "order_qty": to_int(order.get("order_qty"), 0),
        "order_method": order.get("order_method"),
        "execution_mode": EXECUTION_MODE_PAPER_STRATEGY,
        "source_position_state_id": order.get("source_position_state_id"),
        "latest_sellable_check": latest_sellable_check,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "sizing_policy": SIZING_POLICY,
        "source_type": order.get("source_type"),
        "source_daily_run_id": order.get("source_daily_run_id"),
        "source_daily_position_decision_id": order.get("source_daily_position_decision_id"),
    }


def print_candidate(order, index):
    print(
        f"{index}. id={order['id']} "
        f"plan={order['execution_plan_id']} "
        f"daily_run={order['source_daily_run_id']} "
        f"daily_position_decision={order['source_daily_position_decision_id']} "
        f"position_state={order['source_position_state_id']} "
        f"ticker={order['ticker_code']} "
        f"name={order['stock_name']} "
        f"current_qty={order['current_qty']} "
        f"order_qty={order['order_qty']} "
        f"expected_sell_price={order['expected_sell_price']} "
        f"expected_pnl_rate={order['expected_pnl_rate']} "
        f"reason={order['sell_reason']} "
        f"mode={order['execution_mode']} "
        f"status={order['execution_status']}"
    )


def execute_one_auto_sell(conn, order):
    """
    단일 SELL execution order를 검증한 뒤 MarketConnector 실행 요청 상태로 전환한다.
    실제 주문 제출, connector_order_request 생성, 포지션 sell ordered 변경은 수행하지 않는다.
    """
    execution_order_id = order["id"]

    latest_sellable_check = validate_latest_sellable_quantity(
        conn=conn,
        order=order,
    )

    print()
    print(
        f"[LATEST SELLABLE CHECK] "
        f"ok={latest_sellable_check['ok']} "
        f"reason={latest_sellable_check['reason']} "
        f"strategy_order_qty={latest_sellable_check['strategy_order_qty']} "
        f"latest_quantity={latest_sellable_check['latest_quantity']} "
        f"latest_sellable_quantity={latest_sellable_check['latest_sellable_quantity']}"
    )

    if not latest_sellable_check["ok"]:
        print(
            f"[BLOCKED] execution_order_id={execution_order_id} "
            f"reason={latest_sellable_check['reason']}"
        )
        return None

    updated = mark_execution_order_execution_mode(
        conn=conn,
        execution_order_id=execution_order_id,
        execution_mode=EXECUTION_MODE_PAPER_STRATEGY,
    )

    print(
        f"[MODE] execution_order_id={updated['id']} "
        f"execution_mode={updated['execution_mode']} "
        f"status={updated['execution_status']}"
    )

    requested_payload = build_result_payload(
        order=order,
        latest_sellable_check=latest_sellable_check,
    )
    requested = mark_execution_order_requested(
        conn=conn,
        execution_order_id=execution_order_id,
        result_payload=requested_payload,
    )
    conn.commit()

    print(
        f"[REQUESTED] execution_order_id={requested['id']} "
        f"status={requested['execution_status']} "
        f"mode={requested['execution_mode']} "
        f"connector_order_request_id={requested['connector_order_request_id']} "
        f"action={requested['action_type']} "
        f"source_type={requested['source_type']}"
    )

    return requested


def main():
    args = parse_args()

    if print_non_business_day_no_target("Daily Auto SELL"):
        return

    conn = get_conn()
    conn.autocommit = False

    try:
        orders = get_ready_daily_position_sell_execution_orders(
            conn,
            plan_id=args.plan_id,
            limit=args.limit,
        )

        print_header("[Daily Auto SELL Candidates]")
        print(f"plan_id : {args.plan_id}")
        print(f"limit   : {args.limit}")
        print(f"execute : {args.execute}")
        print(f"count   : {len(orders)}")

        if not orders:
            print()
            print("[WARN] 자동매도 대상 READY SELL 주문이 없음")
            conn.rollback()
            return

        executable_orders = []

        for idx, order in enumerate(orders, start=1):
            print_candidate(order, idx)

            reasons = validate_auto_sell_order(order)

            if reasons:
                print("  BLOCKED")
                for reason in reasons:
                    print(f"  - {reason}")
                continue

            executable_orders.append(order)

        print_header("[Validation Summary]")
        print(f"candidate_count  : {len(orders)}")
        print(f"executable_count : {len(executable_orders)}")

        if not executable_orders:
            print("[WARN] 실행 가능한 자동매도 주문이 없음")
            conn.rollback()
            return

        if not args.execute:
            print()
            print("조회/검증만 완료. REQUESTED 전환은 --execute 필요.")
            conn.rollback()
            return

        print_header("[Auto SELL Execute]")
        print("자동매도는 PAPER_STRATEGY 모드만 허용됨.")
        print("전략 order_qty 그대로 MarketConnector SELL 실행 요청 등록.")

        for order in executable_orders:
            execute_one_auto_sell(conn, order)

        print_header("[DONE]")
        print("Daily Position 자동매도 REQUESTED 전환 완료")

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
