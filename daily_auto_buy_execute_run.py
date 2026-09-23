"""
Entrypoint that marks READY daily BUY execution orders as MarketConnector BUY execution requests.
Strategy Execution only performs the transition to the REQUESTED status, without submitting an actual order.
This is an automatic order request path, so it is not run without explicit approval and confirmation of the target environment.
"""

import argparse
import sys
from pathlib import Path
from datetime import date, datetime, timezone

from execution_db import get_conn
from execution_repository import (
    get_ready_daily_buy_execution_orders,
    mark_execution_order_execution_mode,
    mark_execution_order_requested,
)


EXECUTION_MODE_PAPER_STRATEGY = "PAPER_STRATEGY"
SIZING_POLICY = "PAPER_STRATEGY_FULL_STRATEGY_QTY"

# -------------------------------------------------
# Korean business day guard
# -------------------------------------------------
def _load_kr_holiday_checker():
    """
    If interest_get_holidays.py from port-interest-crawler / port_interest_crawler
    is available, also use its Korean market-holiday / public-holiday check.
    Otherwise, only the weekend check is performed.
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
            # Do not kill the batch because of a holiday-utility error; trust only the weekend check.
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
        description="Auto execute READY Daily BUY Signal orders in PAPER_STRATEGY mode"
    )

    parser.add_argument(
        "--plan-id",
        required=False,
        type=int,
        help="특정 execution_plan_id만 자동매수 실행",
    )

    parser.add_argument(
        "--limit",
        required=False,
        type=int,
        default=20,
        help="자동매수 대상 최대 건수",
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="MarketConnector BUY 실행 요청 등록. 없으면 조회/검증만 수행",
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


def validate_auto_buy_order(order):
    reasons = []

    if order["environment"] != "paper":
        reasons.append(f"paper 환경이 아님: environment={order['environment']}")

    if order["source_type"] != "DAILY_SIGNAL_BUY":
        reasons.append(f"DAILY_SIGNAL_BUY가 아님: source_type={order['source_type']}")

    if order["action_type"] != "BUY":
        reasons.append(f"BUY가 아님: action_type={order['action_type']}")

    if order["execution_status"] != "READY":
        reasons.append(f"READY 상태가 아님: execution_status={order['execution_status']}")

    if order["connector_order_request_id"] is not None:
        reasons.append(
            f"이미 connector_order_request_id가 있음: {order['connector_order_request_id']}"
        )

    if order["execution_mode"] not in ("DRY_RUN", "PAPER_STRATEGY"):
        reasons.append(f"자동매수 허용 execution_mode가 아님: {order['execution_mode']}")

    if to_int(order["order_qty"], 0) <= 0:
        reasons.append(f"order_qty가 0 이하: order_qty={order['order_qty']}")

    if order["order_price"] is None:
        reasons.append("order_price 없음")

    if not order["ticker_code"]:
        reasons.append("ticker_code 없음")

    if not order["account_no"]:
        reasons.append("account_no 없음")

    return reasons


def build_result_payload(order):
    return {
        "source": "daily_auto_buy_execute_run",
        "action": "REQUEST_MARKETCONNECTOR_BUY",
        "execution_order_id": order.get("id"),
        "ticker_code": order.get("ticker_code"),
        "order_qty": to_int(order.get("order_qty"), 0),
        "order_method": order.get("order_method"),
        "execution_mode": EXECUTION_MODE_PAPER_STRATEGY,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "sizing_policy": SIZING_POLICY,
        "source_type": order.get("source_type"),
        "source_daily_run_id": order.get("source_daily_run_id"),
        "source_daily_signal_id": order.get("source_daily_signal_id"),
    }


def print_candidate(order, index):
    print(
        f"{index}. id={order['id']} "
        f"plan={order['execution_plan_id']} "
        f"daily_run={order['source_daily_run_id']} "
        f"daily_signal={order['source_daily_signal_id']} "
        f"ticker={order['ticker_code']} "
        f"name={order['stock_name']} "
        f"qty={order['order_qty']} "
        f"price={order['order_price']} "
        f"mode={order['execution_mode']} "
        f"status={order['execution_status']}"
    )


def execute_one_auto_buy(conn, order):
    """
    Validates a single BUY execution order, then transitions it to the MarketConnector execution request status.
    Strategy Execution does not perform the actual order submission or the connector_order_request creation.
    """
    execution_order_id = order["id"]

    updated = mark_execution_order_execution_mode(
        conn=conn,
        execution_order_id=execution_order_id,
        execution_mode=EXECUTION_MODE_PAPER_STRATEGY,
    )

    print()
    print(
        f"[MODE] execution_order_id={updated['id']} "
        f"execution_mode={updated['execution_mode']} "
        f"status={updated['execution_status']}"
    )

    requested_payload = build_result_payload(order)
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

    if print_non_business_day_no_target("Daily Auto BUY"):
        return

    conn = get_conn()
    conn.autocommit = False

    try:
        orders = get_ready_daily_buy_execution_orders(
            conn,
            plan_id=args.plan_id,
            limit=args.limit,
        )

        print_header("[Daily Auto BUY Candidates]")
        print(f"plan_id : {args.plan_id}")
        print(f"limit   : {args.limit}")
        print(f"execute : {args.execute}")
        print(f"count   : {len(orders)}")

        if not orders:
            print()
            print("[WARN] 자동매수 대상 READY Daily BUY 주문이 없음")
            conn.rollback()
            return

        executable_orders = []

        for idx, order in enumerate(orders, start=1):
            print_candidate(order, idx)

            reasons = validate_auto_buy_order(order)

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
            print("[WARN] 실행 가능한 자동매수 주문이 없음")
            conn.rollback()
            return

        if not args.execute:
            print()
            print("조회/검증만 완료. REQUESTED 전환은 --execute 필요.")
            conn.rollback()
            return

        print_header("[Auto BUY Execute]")
        print("자동매수는 PAPER_STRATEGY 모드만 허용됨.")
        print("전략 order_qty 그대로 MarketConnector BUY 실행 요청 등록.")

        for order in executable_orders:
            execute_one_auto_buy(conn, order)

        print_header("[DONE]")
        print("Daily Signal 자동매수 REQUESTED 전환 완료")

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
