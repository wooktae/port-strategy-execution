"""
READY 상태의 SELL execution order를 connector SELL 요청으로 제출하는 entrypoint.
daily position sell과 intraday stop sell 주문을 모두 다룰 수 있으며 포지션 상태를 갱신한다.
자동 매도 경로이므로 명시 승인과 대상 환경 확인 없이 실행하지 않는다.
"""

import argparse
import sys
from pathlib import Path
from datetime import date

from execution_db import get_conn
from execution_config import STRATEGY_NAME, STRATEGY_VERSION
from execution_repository import (
    get_ready_daily_position_sell_execution_orders,
    get_latest_connector_position_snapshot,
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
    from connector_sell import sell_stock  # noqa: E402
except ModuleNotFoundError as e:
    print("[IMPORT ERROR]")
    print(f"CONNECTOR_PATH = {CONNECTOR_PATH}")
    print(f"sys.path[0]    = {sys.path[0]}")
    print("connector_sell.py 파일이 C:\\Workspaces\\port-marketconnector 아래에 있는지 확인 필요")
    raise e


EXECUTION_MODE_PAPER_STRATEGY = "PAPER_STRATEGY"
SIZING_POLICY = "PAPER_STRATEGY_FULL_STRATEGY_QTY"
SUPPORTED_AUTO_SELL_SOURCE_TYPES = {
    "DAILY_POSITION_SELL",
    "INTRADAY_STOP_SELL",
}

ACCEPTED_REQUEST_STATUSES = {"SUBMITTED", "ACCEPTED", "ORDERED"}

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
        help="실제 Connector SELL 주문 실행. 없으면 조회/검증만 수행",
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


def normalize_status(value):
    if value is None:
        return None

    return str(value).strip().upper()


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
    실제 Connector SELL 호출 직전에 최신 connector_position_snapshot 기준으로
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

def build_connector_kwargs(order):
    order_qty = to_int(order.get("order_qty"))

    return {
        "stock_code": order["ticker_code"],
        "qty": order_qty,
        "order_method": order.get("order_method") or "MARKET",
        "order_price": to_float_or_none(order.get("order_price")),
        "stock_name": order.get("stock_name"),
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "strategy_run_id": (
            str(order.get("source_run_id"))
            if order.get("source_run_id") is not None
            else None
        ),
        "strategy_signal_id": order.get("source_daily_position_decision_id"),
        "signal_date": str(order.get("signal_date")) if order.get("signal_date") is not None else None,
        "signal_type": "SELL",
        "signal_score": None,
        "signal_position_size": None,
    }


def is_connector_order_accepted(result):
    if not result:
        return False

    request_status = normalize_status(result.get("request_status"))
    response = result.get("response") or {}
    rt_cd = str(response.get("rt_cd")) if response.get("rt_cd") is not None else None

    if request_status in ACCEPTED_REQUEST_STATUSES:
        return True

    if rt_cd == "0" and result.get("order_request_id") is not None:
        return True

    return False


def build_rejected_error_message(result):
    if not result:
        return "connector SELL result is empty"

    if result.get("error"):
        return str(result.get("error"))

    response_message = result.get("response_message")
    if response_message:
        return str(response_message)

    response = result.get("response") or {}
    msg1 = response.get("msg1")
    if msg1:
        return str(msg1).strip()

    return "connector SELL rejected or unknown response"


def build_result_payload(order, connector_result=None, error=None, latest_sellable_check=None):
    payload = {
        "request_type": "SELL",
        "source": "daily_auto_sell_execute_run",
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,

        "execution_order_id": order.get("id"),
        "execution_plan_id": order.get("execution_plan_id"),
        "execution_mode": EXECUTION_MODE_PAPER_STRATEGY,
        "sizing_policy": SIZING_POLICY,

        "source_type": order.get("source_type"),
        "source_daily_run_id": order.get("source_daily_run_id"),
        "source_daily_position_decision_id": order.get("source_daily_position_decision_id"),
        "source_position_state_id": order.get("source_position_state_id"),

        "ticker_code": order.get("ticker_code"),
        "stock_name": order.get("stock_name"),
        "current_qty": str(order.get("current_qty")) if order.get("current_qty") is not None else None,
        "order_qty": str(order.get("order_qty")) if order.get("order_qty") is not None else None,
        "order_price": str(order.get("order_price")) if order.get("order_price") is not None else None,
        "order_method": order.get("order_method"),

        "expected_sell_price": (
            str(order.get("expected_sell_price"))
            if order.get("expected_sell_price") is not None
            else None
        ),
        "expected_pnl_amount": (
            str(order.get("expected_pnl_amount"))
            if order.get("expected_pnl_amount") is not None
            else None
        ),
        "expected_pnl_rate": (
            str(order.get("expected_pnl_rate"))
            if order.get("expected_pnl_rate") is not None
            else None
        ),
        "sell_reason": order.get("sell_reason"),

        "environment": order.get("environment"),
        "latest_sellable_check": latest_sellable_check,

        "auto_execute": True,
        "auto_execute_type": "DAILY_POSITION_SELL_PAPER_STRATEGY",

        "connector_acceptance_check": {
            "accepted": is_connector_order_accepted(connector_result),
            "request_status": connector_result.get("request_status") if connector_result else None,
            "response_code": connector_result.get("response_code") if connector_result else None,
            "response_message": connector_result.get("response_message") if connector_result else None,
            "broker_order_no": connector_result.get("broker_order_no") if connector_result else None,
            "broker_branch_code": connector_result.get("broker_branch_code") if connector_result else None,
            "order_request_id": connector_result.get("order_request_id") if connector_result else None,
        },
        
    }

    if connector_result is not None:
        payload["connector_result"] = connector_result

    if error is not None:
        payload["error"] = error

    return payload


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
    단일 SELL execution order를 검증한 뒤 connector SELL을 호출하고 결과를 DB에 반영한다.
    성공 시 strategy_position_state를 SELL_ORDERED로 바꾸는 경로가 포함된다.
    """
    execution_order_id = order["id"]

    # -------------------------------------------------
    # 1. execution_mode를 PAPER_STRATEGY로 전환
    # -------------------------------------------------
    updated = mark_execution_order_execution_mode(
        conn=conn,
        execution_order_id=execution_order_id,
        execution_mode=EXECUTION_MODE_PAPER_STRATEGY,
    )
    conn.commit()

    print()
    print(
        f"[MODE] execution_order_id={updated['id']} "
        f"execution_mode={updated['execution_mode']} "
        f"status={updated['execution_status']}"
    )

    # -------------------------------------------------
    # 2. 실제 Connector SELL 호출 직전 최신 매도가능수량 재검증
    # -------------------------------------------------
    latest_sellable_check = validate_latest_sellable_quantity(
        conn=conn,
        order=order,
    )

    print(
        f"[LATEST SELLABLE CHECK] "
        f"ok={latest_sellable_check['ok']} "
        f"reason={latest_sellable_check['reason']} "
        f"strategy_order_qty={latest_sellable_check['strategy_order_qty']} "
        f"latest_quantity={latest_sellable_check['latest_quantity']} "
        f"latest_sellable_quantity={latest_sellable_check['latest_sellable_quantity']}"
    )

    if not latest_sellable_check["ok"]:
        failed_payload = build_result_payload(
            order=order,
            connector_result=None,
            error=latest_sellable_check["reason"],
            latest_sellable_check=latest_sellable_check,
        )

        failed = mark_execution_order_execute_failed(
            conn=conn,
            execution_order_id=execution_order_id,
            result_payload=failed_payload,
        )

        conn.commit()

        print(
            f"[FAILED] execution_order_id={failed['id']} "
            f"status={failed['execution_status']} "
            f"reason={latest_sellable_check['reason']}"
        )

        return failed

    # -------------------------------------------------
    # 3. Connector SELL 호출
    # -------------------------------------------------
    kwargs = build_connector_kwargs(order)

    print(
        f"[CONNECTOR SELL] "
        f"ticker={order['ticker_code']} "
        f"name={order['stock_name']} "
        f"qty={kwargs['qty']} "
        f"policy={SIZING_POLICY}"
    )

    result = sell_stock(**kwargs)

    # -------------------------------------------------
    # 3. Connector 결과 판정
    # -------------------------------------------------
    if not is_connector_order_accepted(result):
        error_message = build_rejected_error_message(result)

        failed_payload = build_result_payload(
            order=order,
            connector_result=result,
            error=error_message,
            latest_sellable_check=latest_sellable_check,
        )

        failed = mark_execution_order_execute_failed(
            conn,
            execution_order_id,
            failed_payload,
            connector_order_request_id=(
                result.get("order_request_id")
                if result
                else None
            ),
        )
        conn.commit()

        print(
            f"[FAILED] execution_order_id={failed['id']} "
            f"status={failed['execution_status']} "
            f"connector_order_request_id={result.get('order_request_id') if result else None}"
        )
        print(f"reason={error_message}")
        print(result)
        return failed

    # -------------------------------------------------
    # 4. 접수 성공 시 SUBMITTED 저장
    # -------------------------------------------------
    submitted_payload = build_result_payload(
        order=order,
        connector_result=result,
        latest_sellable_check=latest_sellable_check,
    )

    submitted = mark_execution_order_submitted(
        conn,
        execution_order_id,
        result["order_request_id"],
        submitted_payload,
    )

    if order.get("source_position_state_id"):
        mark_position_sell_ordered(
            conn,
            order["source_position_state_id"],
        )

    conn.commit()

    print(
        f"[SUBMITTED] execution_order_id={submitted['id']} "
        f"status={submitted['execution_status']} "
        f"mode={submitted['execution_mode']} "
        f"connector_order_request_id={submitted['connector_order_request_id']} "
        f"broker_order_no={result.get('broker_order_no')}"
    )

    return submitted


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
            print("조회/검증만 완료. 실제 자동매도 실행은 --execute 필요.")
            conn.rollback()
            return

        print_header("[Auto SELL Execute]")
        print("자동매도는 PAPER_STRATEGY 모드만 허용됨.")
        print("전략 order_qty 그대로 Connector SELL 호출.")

        for order in executable_orders:
            execute_one_auto_sell(conn, order)

        print_header("[DONE]")
        print("Daily Position 자동매도 실행 완료")

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
